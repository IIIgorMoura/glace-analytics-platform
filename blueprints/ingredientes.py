from flask import Blueprint, render_template, request, jsonify
import sqlite3

ingredientes_bp = Blueprint('ingredientes', __name__)

def get_db_connection():
    conn = sqlite3.connect('glace.db')
    conn.row_factory = sqlite3.Row
    return conn

@ingredientes_bp.route('/')
def index():
    conn = get_db_connection()
    ingredientes_raw = conn.execute('SELECT * FROM ingredientes').fetchall()
    
    ingredientes = []
    abaixo_minimo = 0
    
    for ing in ingredientes_raw:
        estoque_min = ing['estoque_minimo'] if 'estoque_minimo' in ing.keys() else 5.0
        is_baixo = ing['quantidade'] < estoque_min
        
        if is_baixo or ing['quantidade'] == 0:
            abaixo_minimo += 1
            
        ingredientes.append({
            'id': ing['id'],
            'nome': ing['nome'],
            'quantidade': ing['quantidade'],
            'un_medida': ing['un_medida'],
            'custo_medio_base': ing['custo_medio_base'],
            'estoque_baixo': is_baixo,
            'zerado': ing['quantidade'] == 0,
            'estoque_minimo': estoque_min
        })
        
    conn.close()
    
    return render_template('index.html', ingredientes=ingredientes, alertas=abaixo_minimo, active='ingredientes')

@ingredientes_bp.route('/scanner')
def scanner():
    return render_template('scanner.html')

# API para buscar sugestões de autocompletar no modal de entrada
@ingredientes_bp.route('/api/ingredientes/buscar', methods=['GET'])
def buscar_ingredientes():
    termo = request.args.get('q', '')
    conn = get_db_connection()
    resultados = conn.execute(
        "SELECT id, nome FROM ingredientes WHERE nome LIKE ? LIMIT 10", 
        ('%' + termo + '%',)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in resultados])

# API para checar GTIN na tabela vinculada
@ingredientes_bp.route('/api/gtin/<gtin>', methods=['GET'])
def check_gtin(gtin):
    conn = get_db_connection()
    # Busca na tabela nova gtin_ingredientes fazendo JOIN com ingredientes
    assoc = conn.execute('''
        SELECT g.*, i.nome, i.un_medida 
        FROM gtin_ingredientes g 
        JOIN ingredientes i ON g.ingrediente_id = i.id 
        WHERE g.gtin = ?
    ''', (gtin,)).fetchone()
    conn.close()
    
    if assoc:
        return jsonify({
            'existe': True, 
            'id': assoc['ingrediente_id'], 
            'nome': assoc['nome'],
            'un_medida': assoc['un_medida'],
            'conteudo_por_embalagem': assoc['conteudo_por_embalagem']
        })
    return jsonify({'existe': False})

@ingredientes_bp.route('/api/ingredientes/entrada', methods=['POST'])
def entrada_ingrediente():
    data = request.json
    gtin = data.get('gtin', '').strip()
    ingrediente_id = data.get('ingrediente_id')
    nome = data.get('nome', '').strip()
    un_medida = data.get('un_medida')
    conteudo_por_emb = float(data.get('conteudo_por_embalagem', 0))
    qtd_embalagens = float(data.get('qtd_embalagens', 0))
    preco_por_emb = float(data.get('preco_por_embalagem', 0))

    if not nome or conteudo_por_emb <= 0 or qtd_embalagens <= 0 or preco_por_emb <= 0:
        return jsonify({'erro': 'Preencha todos os campos obrigatórios corretamente.'}), 400

    quantidade_adicionada = qtd_embalagens * conteudo_por_emb
    custo_unitario_novo = preco_por_emb / conteudo_por_emb # Preço por grama/ml/unidade base

    conn = get_db_connection()
    cursor = conn.cursor()

    # Previne erro de duplicação caso o ID não venha mas o nome já exista
    if not ingrediente_id and nome:
        existente = cursor.execute('SELECT id FROM ingredientes WHERE nome = ?', (nome,)).fetchone()
        if existente:
            ingrediente_id = existente['id']

    if ingrediente_id:
        ing = cursor.execute('SELECT quantidade, custo_medio_base FROM ingredientes WHERE id = ?', (ingrediente_id,)).fetchone()
        qtd_atual = ing['quantidade']
        cmpm_atual = ing['custo_medio_base']

        nova_qtd_total = qtd_atual + quantidade_adicionada
        if nova_qtd_total > 0:
            novo_cmpm = ((qtd_atual * cmpm_atual) + (quantidade_adicionada * custo_unitario_novo)) / nova_qtd_total
        else:
            novo_cmpm = custo_unitario_novo

        cursor.execute('''
            UPDATE ingredientes 
            SET quantidade = ?, custo_medio_base = ? 
            WHERE id = ?
        ''', (nova_qtd_total, novo_cmpm, ingrediente_id))
    else:
        # Criar novo ingrediente base
        cursor.execute('''
            INSERT INTO ingredientes (nome, quantidade, un_medida, custo_medio_base, estoque_minimo) 
            VALUES (?, ?, ?, ?, 5.0)
        ''', (nome, quantidade_adicionada, un_medida, custo_unitario_novo))
        ingrediente_id = cursor.lastrowid

    # Registra o preço na tabela historico_precos para a margem da receita
    cursor.execute('''
        INSERT INTO historico_precos (ingrediente_id, preco_unitario) 
        VALUES (?, ?)
    ''', (ingrediente_id, custo_unitario_novo))

    # Vincula o GTIN com segurança
    if gtin:
        try:
            existe_gtin = cursor.execute('SELECT id FROM gtin_ingredientes WHERE gtin = ?', (gtin,)).fetchone()
            if not existe_gtin:
                cursor.execute('''
                    INSERT INTO gtin_ingredientes (ingrediente_id, gtin, conteudo_por_embalagem) 
                    VALUES (?, ?, ?)
                ''', (ingrediente_id, gtin, conteudo_por_emb))
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()
    return jsonify({'status': 'sucesso'})

# Rota PUT para atualizar quantidade direta ou estoque mínimo pelo Modal de Edição
@ingredientes_bp.route('/api/ingredientes/<int:item_id>', methods=['PUT'])
def atualizar_ingrediente(item_id):
    data = request.json
    nova_quantidade = max(0.0, float(data.get('quantidade', 0)))
    novo_estoque_minimo = max(0.0, float(data.get('estoque_minimo', 5.0)))
    
    conn = get_db_connection()
    # Verifica se a coluna estoque_minimo existe antes para evitar erros em bancos legados
    try:
        conn.execute('UPDATE ingredientes SET quantidade = ?, estoque_minimo = ? WHERE id = ?', 
                     (nova_quantidade, novo_estoque_minimo, item_id))
    except sqlite3.OperationalError:
        # Fallback caso a tabela antiga do banco ainda não possua a coluna estoque_minimo criada
        conn.execute('ALTER TABLE ingredientes ADD COLUMN estoque_minimo REAL DEFAULT 5.0')
        conn.execute('UPDATE ingredientes SET quantidade = ?, estoque_minimo = ? WHERE id = ?', 
                     (nova_quantidade, novo_estoque_minimo, item_id))
        
    conn.commit()
    conn.close()
    return jsonify({'status': 'sucesso'})

@ingredientes_bp.route('/api/ingredientes/<int:item_id>', methods=['DELETE'])
def deletar_ingrediente(item_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM gtin_ingredientes WHERE ingrediente_id = ?', (item_id,))
    cursor.execute('DELETE FROM ingredientes WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'sucesso'})
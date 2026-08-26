from flask import Blueprint, render_template, request, jsonify
import sqlite3

receitas_bp = Blueprint('receitas', __name__)

def get_db_connection():
    conn = sqlite3.connect('glace.db')
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON;')
    return conn

def calcular_custo_medio(ingrediente_id):
    conn = get_db_connection()
    ing = conn.execute('SELECT custo_medio_base FROM ingredientes WHERE id = ?', (ingrediente_id,)).fetchone()
    conn.close()
    if not ing: 
        return 0.0
    return ing['custo_medio_base']

@receitas_bp.route('/receitas')
def receitas():
    conn = get_db_connection()
    categorias_raw = conn.execute('SELECT * FROM categorias_receitas').fetchall()
    
    categorias = []
    for cat in categorias_raw:
        receitas_raw = conn.execute('SELECT * FROM receitas WHERE categoria_id = ?', (cat['id'],)).fetchall()
        
        lista_receitas = []
        for rec in receitas_raw:
            ings = conn.execute('''
                SELECT RI.quantidade, I.nome, I.un_medida, I.id as ingrediente_id 
                FROM receita_ingredientes RI
                JOIN ingredientes I ON RI.ingrediente_id = I.id
                WHERE RI.receita_id = ?
            ''', (rec['id'],)).fetchall()
            
            custo_total = 0.0
            for ing in ings:
                custo_unitario = calcular_custo_medio(ing['ingrediente_id'])
                custo_total += custo_unitario * ing['quantidade']
            
            preco_venda = rec['preco_venda']
            margem = 0.0
            if preco_venda > 0:
                margem = ((preco_venda - custo_total) / preco_venda) * 100

            lista_receitas.append({
                'id': rec['id'],
                'categoria_id': rec['categoria_id'],
                'nome': rec['nome'],
                'preco_venda': preco_venda,
                'custo': round(custo_total, 2),
                'margem': round(margem, 1),
                'tempo': rec['tempo'],
                'preparo': rec['preparo'],
                'ingredientes': [{'id': ing['ingrediente_id'], 'quantidade': ing['quantidade']} for ing in ings]
            })
            
        categorias.append({
            'id': cat['id'],
            'nome': cat['nome'],
            'receitas': lista_receitas
        })

    # Busca receitas sem categoria (categoria_id IS NULL)
    receitas_sem_cat_raw = conn.execute('SELECT * FROM receitas WHERE categoria_id IS NULL').fetchall()
    if receitas_sem_cat_raw:
        lista_sem_cat = []
        for rec in receitas_sem_cat_raw:
            ings = conn.execute('''
                SELECT RI.quantidade, I.nome, I.un_medida, I.id as ingrediente_id 
                FROM receita_ingredientes RI
                JOIN ingredientes I ON RI.ingrediente_id = I.id
                WHERE RI.receita_id = ?
            ''', (rec['id'],)).fetchall()
            
            custo_total = sum(calcular_custo_medio(ing['ingrediente_id']) * ing['quantidade'] for ing in ings)
            preco_venda = rec['preco_venda']
            margem = ((preco_venda - custo_total) / preco_venda * 100) if preco_venda > 0 else 0.0

            lista_sem_cat.append({
                'id': rec['id'],
                'categoria_id': None,
                'nome': rec['nome'],
                'preco_venda': preco_venda,
                'custo': round(custo_total, 2),
                'margem': round(margem, 1),
                'tempo': rec['tempo'],
                'preparo': rec['preparo'],
                'ingredientes': [{'id': ing['ingrediente_id'], 'quantidade': ing['quantidade']} for ing in ings]
            })
        categorias.append({
            'id': None,
            'nome': 'Sem Categoria',
            'receitas': lista_sem_cat
        })
        
    # Converte rows para lista de dicionarios
    ingredientes_disponiveis = [dict(ing) for ing in conn.execute('SELECT id, nome, un_medida FROM ingredientes').fetchall()]
    conn.close()
    
    return render_template('receitas.html', categorias=categorias, ingredientes_disponiveis=ingredientes_disponiveis, active='receitas')

@receitas_bp.route('/api/categorias', methods=['POST'])
def criar_categoria():
    data = request.get_json(silent=True) or {}
    nome_categoria = data.get('nome')
    
    if not nome_categoria:
        return jsonify({'erro': 'Nome da categoria é obrigatório'}), 400
        
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO categorias_receitas (nome) VALUES (?)', (nome_categoria,))
        conn.commit()
        conn.close()
        return jsonify({'status': 'sucesso', 'mensagem': 'Categoria criada com sucesso!'})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'erro': 'Essa categoria já existe.'}), 400

@receitas_bp.route('/api/receitas/salvar', methods=['POST'])
def salvar_receita():
    data = request.json or {}
    nome = data.get('nome')
    categoria_id = data.get('categoria_id')
    preco_venda = float(data.get('preco_venda', 0))
    tempo = int(data.get('tempo', 0))
    preparo = data.get('preparo', '')
    ingredientes_usados = data.get('ingredientes', [])
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO receitas (categoria_id, nome, preco_venda, tempo, preparo) 
        VALUES (?, ?, ?, ?, ?)
    ''', (categoria_id, nome, preco_venda, tempo, preparo))
    receita_id = cursor.lastrowid
    
    for ing in ingredientes_usados:
        cursor.execute('''
            INSERT INTO receita_ingredientes (receita_id, ingrediente_id, quantidade) 
            VALUES (?, ?, ?)
        ''', (receita_id, ing['id'], float(ing['quantidade'])))
        
    conn.commit()
    conn.close()
    return jsonify({'status': 'sucesso', 'mensagem': 'Receita salva com sucesso!'})

@receitas_bp.route('/api/receitas/atualizar/<int:id>', methods=['PUT'])
def atualizar_receita(id):
    data = request.json or {}
    nome = data.get('nome')
    categoria_id = data.get('categoria_id')
    preco_venda = float(data.get('preco_venda', 0))
    tempo = int(data.get('tempo', 0))
    preparo = data.get('preparo', '')
    ingredientes_usados = data.get('ingredientes', [])
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE receitas SET categoria_id = ?, nome = ?, preco_venda = ?, tempo = ?, preparo = ?
        WHERE id = ?
    ''', (categoria_id, nome, preco_venda, tempo, preparo, id))
    
    cursor.execute('DELETE FROM receita_ingredientes WHERE receita_id = ?', (id,))
    for ing in ingredientes_usados:
        cursor.execute('''
            INSERT INTO receita_ingredientes (receita_id, ingrediente_id, quantidade) 
            VALUES (?, ?, ?)
        ''', (id, ing['id'], float(ing['quantidade'])))
        
    conn.commit()
    conn.close()
    return jsonify({'status': 'sucesso', 'mensagem': 'Receita atualizada com sucesso!'})

@receitas_bp.route('/api/receitas/<int:id>', methods=['DELETE'])
def deletar_receita(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM receitas WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'sucesso'})

@receitas_bp.route('/api/categorias/<int:id>', methods=['DELETE'])
def deletar_categoria(id):
    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM categorias_receitas WHERE id = ?', (id,))
        conn.commit()
        conn.close()
        return jsonify({'status': 'sucesso'})
    except Exception as e:
        conn.close()
        return jsonify({'erro': str(e)}), 400
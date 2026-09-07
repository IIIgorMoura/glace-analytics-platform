from flask import Blueprint, render_template, request, jsonify
import sqlite3
from datetime import date

pedidos_bp = Blueprint('pedidos', __name__)

def get_db_connection():
    conn = sqlite3.connect('glace.db')
    conn.row_factory = sqlite3.Row
    return conn

@pedidos_bp.route('/pedidos')
def index():
    conn = get_db_connection()
    
    # Atualização automática para status 'Atrasado' se data_entrega < hoje e status for 'Pendente'
    hoje = date.today().isoformat()
    conn.execute('''
        UPDATE pedidos 
        SET status = 'Atrasado' 
        WHERE status = 'Pendente' AND data_entrega IS NOT NULL AND data_entrega < ?
    ''', (hoje,))
    conn.commit()
    
    # Captura o filtro de status enviado pela URL (ex: /pedidos?status=Pendente)
    status_filtro = request.args.get('status', 'Todos')
    
    query = '''
        SELECT p.*, GROUP_CONCAT(ip.quantidade || 'x ' || r.nome, ', ') as itens_nomes
        FROM pedidos p
        LEFT JOIN itens_pedido ip ON p.id = ip.pedido_id
        LEFT JOIN receitas r ON ip.receita_id = r.id
    '''
    params = []
    
    if status_filtro and status_filtro != 'Todos':
        query += ' WHERE p.status = ?'
        params.append(status_filtro)
        
    query += ' GROUP BY p.id ORDER BY p.data_pedido DESC'
    
    pedidos = conn.execute(query, params).fetchall()
    
    receitas_raw = conn.execute('SELECT id, nome, preco_venda FROM receitas').fetchall()
    receitas = [dict(row) for row in receitas_raw]
    
    conn.close()
    
    return render_template('pedidos.html', 
                           pedidos=pedidos, 
                           receitas=receitas, 
                           status_atual=status_filtro,
                           active='pedidos')

@pedidos_bp.route('/api/pedidos/status', methods=['POST'])
def atualizar_status():
    data = request.json
    pedido_id = data.get('id')
    novo_status = data.get('status')
    
    if not pedido_id or not novo_status:
        return jsonify({'erro': 'Dados incompletos'}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Verificar status anterior
        pedido_atual = cursor.execute('SELECT status FROM pedidos WHERE id = ?', (pedido_id,)).fetchone()
        if not pedido_atual:
            conn.close()
            return jsonify({'erro': 'Pedido não encontrado'}), 404
            
        status_antigo = pedido_atual['status']
        
        # Se mudou para 'Entregue' pela primeira vez, dar baixa no estoque de ingredientes
        if novo_status == 'Entregue' and status_antigo != 'Entregue':
            itens = cursor.execute('''
                SELECT receita_id, quantidade FROM itens_pedido WHERE pedido_id = ?
            ''', (pedido_id,)).fetchall()
            
            for item in itens:
                receita_id = item['receita_id']
                qtd_pedido = item['quantidade']
                
                # Ingredientes necessários para essa receita
                ingredientes_receita = cursor.execute('''
                    SELECT ingrediente_id, quantidade FROM receita_ingredientes WHERE receita_id = ?
                ''', (receita_id,)).fetchall()
                
                for ing in ingredientes_receita:
                    ing_id = ing['ingrediente_id']
                    qtd_necessaria = ing['quantidade'] * qtd_pedido
                    
                    # Subtrair do estoque (garantindo que não fique negativo)
                    cursor.execute('''
                        UPDATE ingredientes 
                        SET quantidade = MAX(0, quantidade - ?) 
                        WHERE id = ?
                    ''', (qtd_necessaria, ing_id))

        cursor.execute('UPDATE pedidos SET status = ? WHERE id = ?', (novo_status, pedido_id))
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        conn.close()
        return jsonify({'erro': str(e)}), 500
        
    conn.close()
    return jsonify({'status': 'sucesso'})

@pedidos_bp.route('/api/pedidos/lista-compras', methods=['GET'])
def lista_compras():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Soma a quantidade necessária de ingredientes para pedidos pendentes/ativos (diferente de Entregue e Cancelado)
    necessarios_raw = cursor.execute('''
        SELECT ri.ingrediente_id, SUM(ri.quantidade * ip.quantidade) as total_necessario
        FROM pedidos p
        JOIN itens_pedido ip ON p.id = ip.pedido_id
        JOIN receita_ingredientes ri ON ip.receita_id = ri.receita_id
        WHERE p.status NOT IN ('Entregue', 'Cancelado')
        GROUP BY ri.ingrediente_id
    ''').fetchall()
    
    necessidades = {row['ingrediente_id']: row['total_necessario'] for row in necessarios_raw}
    
    # Busca estoque atual e custo base de cada ingrediente
    ingredientes = cursor.execute('SELECT id, nome, quantidade, un_medida, custo_medio_base FROM ingredientes').fetchall()
    
    lista = []
    custo_total = 0
    
    for ing in ingredientes:
        ing_id = ing['id']
        estoque_atual = ing['quantidade']
        necessario = necessidades.get(ing_id, 0)
        
        if estoque_atual < necessario:
            falta = necessario - estoque_atual
            custo_unit = ing['custo_medio_base'] or 0
            custo_item = falta * custo_unit
            custo_total += custo_item
            
            lista.append({
                'nome': ing['nome'],
                'estoque': estoque_atual,
                'necessario': necessario,
                'falta': falta,
                'un_medida': ing['un_medida'],
                'custo_estimado': custo_item
            })
            
    conn.close()
    return jsonify({
        'lista': lista,
        'custo_total': custo_total
    })
@pedidos_bp.route('/api/pedidos/novo', methods=['POST'])
def novo_pedido():
    data = request.json
    cliente = data.get('cliente_nome', 'Cliente Padrão')
    data_entrega = data.get('data_entrega') 
    itens = data.get('itens', [])
    
    if not itens:
        return jsonify({'erro': 'O pedido precisa ter pelo menos um item.'}), 400

    valor_total = sum(float(item['quantidade']) * float(item['preco_unitario']) for item in itens)

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO pedidos (cliente_nome, data_entrega, valor_total) 
            VALUES (?, ?, ?)
        ''', (cliente, data_entrega, valor_total))
        
        pedido_id = cursor.lastrowid
        
        for item in itens:
            cursor.execute('''
                INSERT INTO itens_pedido (pedido_id, receita_id, quantidade, preco_unitario)
                VALUES (?, ?, ?, ?)
            ''', (pedido_id, item['receita_id'], item['quantidade'], item['preco_unitario']))
            
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        conn.close()
        return jsonify({'erro': f'Erro ao salvar no banco: {str(e)}'}), 500
        
    conn.close()
    return jsonify({'status': 'sucesso', 'pedido_id': pedido_id})

@pedidos_bp.route('/api/pedidos/<int:pedido_id>', methods=['GET'])
def get_pedido(pedido_id):
    conn = get_db_connection()
    pedido = conn.execute('SELECT * FROM pedidos WHERE id = ?', (pedido_id,)).fetchone()
    if not pedido:
        return jsonify({'erro': 'Pedido não encontrado'}), 404
    
    itens_raw = conn.execute('''
        SELECT ip.receita_id, ip.quantidade, ip.preco_unitario, r.nome
        FROM itens_pedido ip
        JOIN receitas r ON ip.receita_id = r.id
        WHERE ip.pedido_id = ?
    ''', (pedido_id,)).fetchall()
    conn.close()
    
    return jsonify({
        'id': pedido['id'],
        'cliente_nome': pedido['cliente_nome'],
        'data_entrega': pedido['data_entrega'],
        'status': pedido['status'],
        'itens': [dict(row) for row in itens_raw]
    })

@pedidos_bp.route('/api/pedidos/<int:pedido_id>/editar', methods=['POST'])
def editar_pedido(pedido_id):
    data = request.json
    cliente = data.get('cliente_nome')
    data_entrega = data.get('data_entrega')
    itens = data.get('itens', [])
    
    if not itens:
        return jsonify({'erro': 'O pedido precisa ter pelo menos um item.'}), 400

    valor_total = sum(float(item['quantidade']) * float(item['preco_unitario']) for item in itens)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE pedidos 
            SET cliente_nome = ?, data_entrega = ?, valor_total = ?
            WHERE id = ?
        ''', (cliente, data_entrega, valor_total, pedido_id))
        
        cursor.execute('DELETE FROM itens_pedido WHERE pedido_id = ?', (pedido_id,))
        for item in itens:
            cursor.execute('''
                INSERT INTO itens_pedido (pedido_id, receita_id, quantidade, preco_unitario)
                VALUES (?, ?, ?, ?)
            ''', (pedido_id, item['receita_id'], item['quantidade'], item['preco_unitario']))
            
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        conn.close()
        return jsonify({'erro': str(e)}), 500
        
    conn.close()
    return jsonify({'status': 'sucesso'})

@pedidos_bp.route('/api/pedidos/<int:pedido_id>/excluir', methods=['POST'])
def excluir_pedido(pedido_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM itens_pedido WHERE pedido_id = ?', (pedido_id,))
        cursor.execute('DELETE FROM pedidos WHERE id = ?', (pedido_id,))
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        conn.close()
        return jsonify({'erro': str(e)}), 500
        
    conn.close()
    return jsonify({'status': 'sucesso'})
from flask import Blueprint, render_template, request, jsonify
import sqlite3

pedidos_bp = Blueprint('pedidos', __name__)

def get_db_connection():
    conn = sqlite3.connect('glace.db')
    conn.row_factory = sqlite3.Row
    return conn

@pedidos_bp.route('/pedidos')
def index():
    conn = get_db_connection()
    
    # Nova query que busca os pedidos e junta a quantidade com o nome (Ex: 2x Pavê)
    pedidos = conn.execute('''
        SELECT p.*, GROUP_CONCAT(ip.quantidade || 'x ' || r.nome, ', ') as itens_nomes
        FROM pedidos p
        LEFT JOIN itens_pedido ip ON p.id = ip.pedido_id
        LEFT JOIN receitas r ON ip.receita_id = r.id
        GROUP BY p.id
        ORDER BY p.data_pedido DESC
    ''').fetchall()
    
    # Busca as receitas para popular o modal de "Novo Pedido" e converte para dicionário
    receitas_raw = conn.execute('SELECT id, nome, preco_venda FROM receitas').fetchall()
    receitas = [dict(row) for row in receitas_raw]
    
    conn.close()
    
    return render_template('pedidos.html', 
                           pedidos=pedidos, 
                           receitas=receitas, 
                           active='pedidos')

@pedidos_bp.route('/api/pedidos/status', methods=['POST'])
def atualizar_status():
    data = request.json
    pedido_id = data.get('id')
    novo_status = data.get('status')
    
    if not pedido_id or not novo_status:
        return jsonify({'erro': 'Dados incompletos'}), 400
        
    conn = get_db_connection()
    try:
        conn.execute('UPDATE pedidos SET status = ? WHERE id = ?', (novo_status, pedido_id))
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        conn.close()
        return jsonify({'erro': str(e)}), 500
        
    conn.close()
    return jsonify({'status': 'sucesso'})

@pedidos_bp.route('/api/pedidos/novo', methods=['POST'])
def novo_pedido():
    data = request.json
    cliente = data.get('cliente_nome', 'Cliente Padrão')
    data_entrega = data.get('data_entrega') 
    itens = data.get('itens', [])
    
    if not itens:
        return jsonify({'erro': 'O pedido precisa ter pelo menos um item.'}), 400

    # Calcula o valor total multiplicando a quantidade pelo preço unitário de cada item
    valor_total = sum(float(item['quantidade']) * float(item['preco_unitario']) for item in itens)

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Insere o pedido na tabela principal
        cursor.execute('''
            INSERT INTO pedidos (cliente_nome, data_entrega, valor_total) 
            VALUES (?, ?, ?)
        ''', (cliente, data_entrega, valor_total))
        
        pedido_id = cursor.lastrowid
        
        # 2. Insere os itens na tabela de relação (itens_pedido)
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
    # Puxa os dados do pedido
    pedido = conn.execute('SELECT * FROM pedidos WHERE id = ?', (pedido_id,)).fetchone()
    if not pedido:
        return jsonify({'erro': 'Pedido não encontrado'}), 404
    
    # Puxa os itens que o cliente pediu (Detalhes do Pedido)
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
        # Atualiza os dados principais do pedido
        cursor.execute('''
            UPDATE pedidos 
            SET cliente_nome = ?, data_entrega = ?, valor_total = ?
            WHERE id = ?
        ''', (cliente, data_entrega, valor_total, pedido_id))
        
        # O jeito mais seguro de atualizar os itens é apagar os antigos e inserir os novos
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

# NOVA ROTA: Excluir Pedido
@pedidos_bp.route('/api/pedidos/<int:pedido_id>/excluir', methods=['POST'])
def excluir_pedido(pedido_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Primeiro exclui as relações na tabela itens_pedido
        cursor.execute('DELETE FROM itens_pedido WHERE pedido_id = ?', (pedido_id,))
        # Depois exclui o pedido da tabela principal
        cursor.execute('DELETE FROM pedidos WHERE id = ?', (pedido_id,))
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        conn.close()
        return jsonify({'erro': str(e)}), 500
        
    conn.close()
    return jsonify({'status': 'sucesso'})
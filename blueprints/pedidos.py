from flask import Blueprint, render_template, request, jsonify

pedidos_bp = Blueprint('pedidos', __name__)

#@pedidos_bp.route('/dashboard')
#def dashboard():

#    return render_template('dashboard.html', active='dashboard')

# Dados estáticos temporários para visualização durante o desenvolvimento
@pedidos_bp.route('/pedidos')
def pedidos():
    pedidos_lista = [
        {'id': 1, 'data_entrega': '18/08/2026', 'cliente': 'Ana Silva', 'pedido': 'Bolo Vulcão de Chocolate', 'valor': 85.00, 'status': 'Pendente'},
        {'id': 2, 'data_entrega': '18/08/2026', 'cliente': 'Carlos Souza', 'pedido': 'Bolos de Pote (Cx 4)', 'valor': 48.00, 'status': 'Pronto'},
        {'id': 3, 'data_entrega': '19/08/2026', 'cliente': 'Mariana Lima', 'pedido': 'Combo Festa', 'valor': 160.00, 'status': 'Atrasado'}
    ]
    return render_template('pedidos.html', pedidos=pedidos_lista, active='pedidos')

@pedidos_bp.route('/api/pedidos/status', methods=['POST'])
def atualizar_status_pedido():
    data = request.json
    pedido_id = data.get('id')
    novo_status = data.get('status')
    return jsonify({'status': 'sucesso', 'pedido_id': pedido_id, 'novo_status': novo_status})
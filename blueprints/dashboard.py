from flask import Blueprint, render_template, request, jsonify
import sqlite3

dashboard_bp = Blueprint('dashboard', __name__)

def get_db_connection():
    conn = sqlite3.connect('glace.db')
    conn.row_factory = sqlite3.Row
    return conn

@dashboard_bp.route('/dashboard')
def dashboard():
    conn = get_db_connection()
    
    try:
        receitas = conn.execute('''
            SELECT r.id, r.nome, r.preco_venda,
                   COALESCE(SUM(ri.quantidade * COALESCE(i.custo_medio_base, 0)), 0) as custo_total
            FROM receitas r
            LEFT JOIN receita_ingredientes ri ON r.id = ri.receita_id
            LEFT JOIN ingredientes i ON ri.ingrediente_id = i.id
            GROUP BY r.id
            ORDER BY r.nome ASC
        ''').fetchall()
    except sqlite3.OperationalError:
        receitas = []
    
    nomes_receitas = []
    custo_pcts = []
    margem_pcts = []
    precos_venda = []
    
    for r in receitas:
        preco = float(r['preco_venda'] or 0)
        custo = float(r['custo_total'] or 0)
        
        if preco > 0:
            c_pct = (custo / preco) * 100
            c_pct_bounded = min(max(c_pct, 0), 100)
            m_pct_bounded = 100 - c_pct_bounded
        else:
            c_pct_bounded = 0.0
            m_pct_bounded = 0.0

        nomes_receitas.append(r['nome'])
        custo_pcts.append(round(c_pct_bounded, 1))
        margem_pcts.append(round(m_pct_bounded, 1))
        precos_venda.append(preco)

    cat_labels = ['Bolos Mini Vulcão', 'Bolos de Pote', 'Combos de Aniversário', 'Doces Gourmet', 'Brownies']
    cat_values = [42.0, 28.5, 15.0, 8.2, 6.3]

    try:
        pedidos_hoje = conn.execute('''
            SELECT COUNT(*) as total 
            FROM pedidos 
            WHERE date(data_pedido) = date('now', 'localtime')
        ''').fetchone()['total']
        
        receita_total = conn.execute('''
            SELECT SUM(valor_total) as receita 
            FROM pedidos 
            WHERE status = 'Entregue'
        ''').fetchone()['receita'] or 0.0
    except sqlite3.OperationalError:
        pedidos_hoje = 0
        receita_total = 0.0

    alertas = []
    
    try:
        # Alerta 1: Estoque Baixo Convencional
        estoque_baixo = conn.execute('''
            SELECT nome, quantidade, un_medida 
            FROM ingredientes 
            WHERE quantidade <= estoque_minimo
        ''').fetchall()
        
        for item in estoque_baixo:
            alertas.append({
                'tipo': 'estoque',
                'texto': f"Estoque crítico: {item['nome']} ({item['quantidade']}{item['un_medida']} restantes)",
                'urgente': True
            })

        # Alerta 2: Pedidos Pendentes ou Atrasados
        pedidos_urgentes = conn.execute('''
            SELECT id, cliente_nome, status 
            FROM pedidos 
            WHERE status IN ('Pendente', 'Atrasado') 
            AND date(data_entrega) <= date('now', 'localtime')
        ''').fetchall()
        
        for ped in pedidos_urgentes:
            urgencia_txt = "Entrega hoje!" if ped['status'] == 'Pendente' else "ATRASADO!"
            alertas.append({
                'tipo': 'pedido',
                'texto': f"Pedido #{ped['id']} ({ped['cliente_nome']}) — {urgencia_txt}",
                'urgente': True
            })

        # Alerta 3: LISTA DE COMPRAS (Demanda vs Estoque)[cite: 1]
        # Pega todos os itens dos pedidos que não estão Entregues ou Cancelados
        demanda_raw = conn.execute('''
            SELECT ri.ingrediente_id, i.nome, i.un_medida, i.quantidade as estoque_atual, i.custo_medio_base,
                   SUM(ip.quantidade * ri.quantidade) as qtd_necessaria
            FROM itens_pedido ip
            JOIN pedidos p ON ip.pedido_id = p.id
            JOIN receita_ingredientes ri ON ip.receita_id = ri.receita_id
            JOIN ingredientes i ON ri.ingrediente_id = i.id
            WHERE p.status NOT IN ('Entregue', 'Cancelado')
            GROUP BY ri.ingrediente_id
        ''').fetchall()

        custo_total_compras = 0.0
        lista_compras_txt = []

        for item in demanda_raw:
            estoque_atual = item['estoque_atual']
            qtd_necessaria = item['qtd_necessaria']
            
            if estoque_atual < qtd_necessaria:
                qtd_faltante = qtd_necessaria - estoque_atual
                custo_estimado = qtd_faltante * item['custo_medio_base']
                custo_total_compras += custo_estimado
                lista_compras_txt.append(f"{item['nome']}: {qtd_faltante:.1f}{item['un_medida']}")

        if lista_compras_txt:
            alertas.append({
                'tipo': 'compras',
                'texto': f"Faltam insumos para pedidos! Comprar: {', '.join(lista_compras_txt[:3])}... (Custo est.: R$ {custo_total_compras:.2f})",
                'urgente': True,
                'is_compras': True,
                'custo_estimado': custo_total_compras
            })
            
    except sqlite3.OperationalError:
        pass 

    qtd_alertas = len(alertas)
    conn.close()
    
    return render_template('dashboard.html', 
                           active='dashboard',
                           nomes_receitas=nomes_receitas,
                           custo_pcts=custo_pcts,
                           margem_pcts=margem_pcts,
                           precos_venda=precos_venda,
                           cat_labels=cat_labels,
                           cat_values=cat_values,
                           pedidos_hoje=pedidos_hoje,
                           receita_total=receita_total,
                           alertas=alertas,
                           qtd_alertas=qtd_alertas)

@dashboard_bp.route('/salvar-custos', methods=['POST'])
def salvar_custos():
    dados = request.get_json()
    mes = dados.get('mes')
    custos = dados.get('custos', [])
    
    if not mes:
        return jsonify({'sucesso': False, 'erro': 'Mês de referência não fornecido'}), 400
        
    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM custos_operacionais WHERE mes_referencia = ?', (mes,))
        for custo in custos:
            conn.execute('''
                INSERT INTO custos_operacionais (mes_referencia, categoria_key, categoria_nome, valor)
                VALUES (?, ?, ?, ?)
            ''', (mes, custo['categoriaKey'], custo['categoriaNome'], custo['valor']))
        conn.commit()
        return jsonify({'sucesso': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'sucesso': False, 'erro': str(e)}), 500
    finally:
        conn.close()

@dashboard_bp.route('/api/custos/<mes>', methods=['GET'])
def obter_custos(mes):
    conn = get_db_connection()
    try:
        custos_db = conn.execute('SELECT * FROM custos_operacionais WHERE mes_referencia = ?', (mes,)).fetchall()
        custos = []
        for c in custos_db:
            custos.append({
                'categoriaKey': c['categoria_key'],
                'categoriaNome': c['categoria_nome'],
                'valor': c['valor']
            })
        return jsonify({'sucesso': True, 'custos': custos})
    except Exception as e:
        return jsonify({'sucesso': False, 'erro': str(e)}), 500
    finally:
        conn.close()
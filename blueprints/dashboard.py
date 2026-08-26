from flask import Blueprint, render_template
import sqlite3

dashboard_bp = Blueprint('dashboard', __name__)

def get_db_connection():
    conn = sqlite3.connect('glace.db')
    conn.row_factory = sqlite3.Row
    return conn

@dashboard_bp.route('/dashboard')
def dashboard():
    conn = get_db_connection()
    
    # 1. Dados para o Gráfico de Margem por Item (Terceiro Gráfico)
    receitas = conn.execute('''
        SELECT r.id, r.nome, r.preco_venda,
               COALESCE(SUM(ri.quantidade * COALESCE(i.custo_medio_base, 0)), 0) as custo_total
        FROM receitas r
        LEFT JOIN receita_ingredientes ri ON r.id = ri.receita_id
        LEFT JOIN ingredientes i ON ri.ingrediente_id = i.id
        GROUP BY r.id
        ORDER BY r.nome ASC
    ''').fetchall()
    
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

    # 2. Dados Estáticos Temporários para o Gráfico de Setores (Lucro por Categoria) para visualização durante desenvolvimento
    cat_labels = ['Bolos Mini Vulcão', 'Bolos de Pote', 'Combos de Aniversário', 'Doces Gourmet', 'Brownies']
    cat_values = [42.0, 28.5, 15.0, 8.2, 6.3]

    conn.close()
    
    return render_template('dashboard.html', 
                           active='dashboard',
                           nomes_receitas=nomes_receitas,
                           custo_pcts=custo_pcts,
                           margem_pcts=margem_pcts,
                           precos_venda=precos_venda,
                           cat_labels=cat_labels,
                           cat_values=cat_values)
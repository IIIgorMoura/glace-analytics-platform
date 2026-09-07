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
    
    # --- GRÁFICO 1: Margem por Item ---
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

    # --- CÁLCULO DE KPIS GERAIS ---
    lucro_bruto = 0.0
    pedidos_pendentes = 0
    margem_lucro_media = 0.0
    
    try:
        pedidos_pendentes = conn.execute("SELECT COUNT(*) as total FROM pedidos WHERE status = 'Pendente'").fetchone()['total']
        
        dados_lucro = conn.execute('''
            WITH CustoReceita AS (
                SELECT ri.receita_id, SUM(ri.quantidade * i.custo_medio_base) as custo_producao
                FROM receita_ingredientes ri
                JOIN ingredientes i ON ri.ingrediente_id = i.id
                GROUP BY ri.receita_id
            )
            SELECT 
                SUM(ip.quantidade * ip.preco_unitario) as receita_entregue,
                SUM(ip.quantidade * cr.custo_producao) as custo_entregue
            FROM pedidos p
            JOIN itens_pedido ip ON p.id = ip.pedido_id
            LEFT JOIN CustoReceita cr ON ip.receita_id = cr.receita_id
            WHERE p.status = 'Entregue'
        ''').fetchone()
        
        if dados_lucro and dados_lucro['receita_entregue']:
            receita_entregue_geral = float(dados_lucro['receita_entregue'])
            custo_entregue_geral = float(dados_lucro['custo_entregue'] or 0.0)
            lucro_bruto = receita_entregue_geral - custo_entregue_geral
            
            if receita_entregue_geral > 0:
                margem_lucro_media = (lucro_bruto / receita_entregue_geral) * 100
                
    except sqlite3.OperationalError:
        pass

    # --- GRÁFICO 2: Receitas Mais Vendidas (Doughnut) ---
    cat_labels = []
    cat_values = []
    
    try:
        top_receitas = conn.execute('''
            SELECT r.nome as receita, SUM(ip.quantidade * ip.preco_unitario) as total_gerado
            FROM pedidos p
            JOIN itens_pedido ip ON p.id = ip.pedido_id
            JOIN receitas r ON ip.receita_id = r.id
            WHERE p.status = 'Entregue'
            GROUP BY r.id
            ORDER BY total_gerado DESC
        ''').fetchall()
        
        for row in top_receitas:
            if row['total_gerado'] and float(row['total_gerado']) > 0:
                cat_labels.append(row['receita'])
                cat_values.append(float(row['total_gerado']))
                
        if not cat_labels:
            cat_labels = ['Nenhuma venda']
            cat_values = [0]
    except sqlite3.OperationalError:
        cat_labels = ['Sem dados']
        cat_values = [0]


    # --- GRÁFICO 3: Evolução Financeira (100% Dinâmico do Banco) ---
    meses_linha = []
    linha_receitas = []
    linha_custos_op = []
    linha_custos_ingredientes = []

    try:
        # Pega todos os meses únicos que existem nos pedidos entregues OU nos custos operacionais
        meses_db = conn.execute('''
            SELECT DISTINCT strftime('%Y-%m', p.data_entrega) as mes
            FROM pedidos p WHERE p.status = 'Entregue' AND p.data_entrega IS NOT NULL
            UNION
            SELECT DISTINCT mes_referencia as mes
            FROM custos_operacionais
            ORDER BY mes ASC
        ''').fetchall()

        meses_nomes = {'01':'Jan', '02':'Fev', '03':'Mar', '04':'Abr', '05':'Mai', '06':'Jun', 
                       '07':'Jul', '08':'Ago', '09':'Set', '10':'Out', '11':'Nov', '12':'Dez'}

        for row in meses_db:
            mes_str = row['mes']
            if not mes_str: continue
            
            # Formata de "2026-09" para "Set/26"
            try:
                ano, mes_num = mes_str.split('-')
                meses_linha.append(f"{meses_nomes.get(mes_num, mes_num)}/{ano[2:]}")
            except:
                meses_linha.append(mes_str)

            # Receita e Custo de Ingredientes EXATOS deste mês
            dados_mes = conn.execute('''
                WITH CustoReceita AS (
                    SELECT ri.receita_id, SUM(ri.quantidade * i.custo_medio_base) as custo_producao
                    FROM receita_ingredientes ri
                    JOIN ingredientes i ON ri.ingrediente_id = i.id
                    GROUP BY ri.receita_id
                )
                SELECT 
                    COALESCE(SUM(ip.quantidade * ip.preco_unitario), 0) as receita_total,
                    COALESCE(SUM(ip.quantidade * cr.custo_producao), 0) as custo_ing
                FROM pedidos p
                JOIN itens_pedido ip ON p.id = ip.pedido_id
                LEFT JOIN CustoReceita cr ON ip.receita_id = cr.receita_id
                WHERE p.status = 'Entregue' AND strftime('%Y-%m', p.data_entrega) = ?
            ''', (mes_str,)).fetchone()
            
            linha_receitas.append(float(dados_mes['receita_total']))
            linha_custos_ingredientes.append(float(dados_mes['custo_ing']))

            # Custo Operacional EXATO deste mês
            custo_op = conn.execute('''
                SELECT COALESCE(SUM(valor), 0) as total
                FROM custos_operacionais
                WHERE mes_referencia = ?
            ''', (mes_str,)).fetchone()
            
            linha_custos_op.append(float(custo_op['total']))

    except sqlite3.OperationalError:
        pass

    # Fallback se o banco estiver 100% vazio (sem nenhum pedido entregue ou custo)
    if not meses_linha:
        meses_linha = ['Sem Registros']
        linha_receitas = [0]
        linha_custos_op = [0]
        linha_custos_ingredientes = [0]


    # --- PAINEL DE ALERTAS & LISTA DE COMPRAS ---
    alertas = []
    gasto_estimado = 0.0
    
    try:
        estoque_baixo = conn.execute('''
            SELECT nome, quantidade, un_medida, estoque_minimo
            FROM ingredientes 
            WHERE quantidade <= estoque_minimo
        ''').fetchall()
        
        for item in estoque_baixo:
            alertas.append({
                'tipo': 'estoque',
                'texto': f"Ruptura de estoque: {item['nome']} atingiu {item['quantidade']}{item['un_medida']} (Mínimo: {item['estoque_minimo']})",
                'urgente': True
            })

        pedidos_urgentes = conn.execute('''
            SELECT id, cliente_nome, status 
            FROM pedidos 
            WHERE status IN ('Pendente', 'Atrasado') 
            AND date(data_entrega) <= date('now', 'localtime')
        ''').fetchall()
        
        for ped in pedidos_urgentes:
            urgencia_txt = "Prazo de entrega para hoje" if ped['status'] == 'Pendente' else "Prazo de entrega expirado (ATRASADO)"
            alertas.append({
                'tipo': 'pedido',
                'texto': f"Pedido #{ped['id']} ({ped['cliente_nome']}) — {urgencia_txt}",
                'urgente': True
            })

        # Cálculo do Gasto Estimado (Lista de Compras)
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

        lista_compras_txt = []

        for item in demanda_raw:
            estoque_atual = item['estoque_atual']
            qtd_necessaria = item['qtd_necessaria']
            
            if estoque_atual < qtd_necessaria:
                qtd_faltante = qtd_necessaria - estoque_atual
                custo_estimado = qtd_faltante * item['custo_medio_base']
                gasto_estimado += custo_estimado
                lista_compras_txt.append(f"{item['nome']}")

        if lista_compras_txt:
            alertas.append({
                'tipo': 'compras',
                'texto': f"Insumos insuficientes para demandas pendentes. Repor: {', '.join(lista_compras_txt[:3])}. (Investimento est.: R$ {gasto_estimado:.2f})",
                'urgente': True
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
                           meses_linha=meses_linha,
                           linha_receitas=linha_receitas,
                           linha_custos_op=linha_custos_op,
                           linha_custos_ingredientes=linha_custos_ingredientes,
                           alertas=alertas,
                           qtd_alertas=qtd_alertas,
                           lucro_bruto=lucro_bruto,
                           pedidos_pendentes=pedidos_pendentes,
                           margem_lucro_media=margem_lucro_media,
                           gasto_estimado=gasto_estimado)

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

@dashboard_bp.route('/api/custos-meses', methods=['GET'])
def obter_meses_custos():
    conn = get_db_connection()
    try:
        meses_db = conn.execute('SELECT DISTINCT mes_referencia FROM custos_operacionais ORDER BY mes_referencia DESC').fetchall()
        meses = [m['mes_referencia'] for m in meses_db]
        return jsonify({'sucesso': True, 'meses': meses})
    except Exception as e:
        return jsonify({'sucesso': False, 'erro': str(e)}), 500
    finally:
        conn.close()
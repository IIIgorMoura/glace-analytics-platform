from flask import Flask
import sqlite3

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('glace.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    
    # 1. Tabela Principal de Ingredientes
    conn.execute('''
        CREATE TABLE IF NOT EXISTS ingredientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            quantidade REAL NOT NULL DEFAULT 0,
            un_medida TEXT NOT NULL,
            custo_medio_base REAL NOT NULL DEFAULT 0,
            estoque_minimo REAL DEFAULT 5.0
        )
    ''')
    
    # 2. Nova Tabela: Múltiplos GTINs para o mesmo Ingrediente
    conn.execute('''
        CREATE TABLE IF NOT EXISTS gtin_ingredientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ingrediente_id INTEGER,
            gtin TEXT UNIQUE NOT NULL,
            conteudo_por_embalagem REAL NOT NULL,
            FOREIGN KEY (ingrediente_id) REFERENCES ingredientes (id) ON DELETE CASCADE
        )
    ''')
    
    # 3. Tabelas de Receitas e Categorias
    conn.execute('''
        CREATE TABLE IF NOT EXISTS categorias_receitas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS receitas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria_id INTEGER,
            nome TEXT NOT NULL,
            preco_venda REAL NOT NULL,
            tempo INTEGER,
            preparo TEXT,
            FOREIGN KEY (categoria_id) REFERENCES categorias_receitas (id) ON DELETE SET NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS receita_ingredientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            receita_id INTEGER,
            ingrediente_id INTEGER,
            quantidade REAL NOT NULL,
            FOREIGN KEY (receita_id) REFERENCES receitas (id) ON DELETE CASCADE,
            FOREIGN KEY (ingrediente_id) REFERENCES ingredientes (id) ON DELETE CASCADE
        )
    ''')

    # 4. Histórico de Preços
    conn.execute('''
        CREATE TABLE IF NOT EXISTS historico_precos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ingrediente_id INTEGER,
            preco_unitario REAL NOT NULL,
            data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ingrediente_id) REFERENCES ingredientes (id) ON DELETE CASCADE
        )
    ''')

    # 5. Tabela de Pedidos Unificada (COM data_entrega)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_nome TEXT,
            data_pedido TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            data_entrega TEXT,
            status TEXT DEFAULT 'Pendente',
            valor_total REAL NOT NULL DEFAULT 0
        )
    ''')
    
    # 6. Tabela de Itens do Pedido
    conn.execute('''
        CREATE TABLE IF NOT EXISTS itens_pedido (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id INTEGER,
            receita_id INTEGER,
            quantidade INTEGER NOT NULL,
            preco_unitario REAL NOT NULL,
            FOREIGN KEY (pedido_id) REFERENCES pedidos (id) ON DELETE CASCADE,
            FOREIGN KEY (receita_id) REFERENCES receitas (id)
        )
    ''')

    # 7. Custos Operacionais (NOVA TABELA)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS custos_operacionais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes_referencia TEXT NOT NULL,
            categoria_key TEXT NOT NULL,
            categoria_nome TEXT NOT NULL,
            valor REAL NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()

# Importar e registrar os Blueprints
from blueprints.ingredientes import ingredientes_bp
from blueprints.pedidos import pedidos_bp
from blueprints.receitas import receitas_bp
from blueprints.dashboard import dashboard_bp 

app.register_blueprint(ingredientes_bp)
app.register_blueprint(pedidos_bp)
app.register_blueprint(receitas_bp)
app.register_blueprint(dashboard_bp)

if __name__ == '__main__':
    init_db()
    # Acesso via rede local habilitado (0.0.0.0)
    app.run(host='0.0.0.0', debug=True, port=5000)
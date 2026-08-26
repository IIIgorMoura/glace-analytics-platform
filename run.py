from flask import Flask
import sqlite3

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('glace.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    
    # 1. Tabela Principal de Ingredientes (Agora com Custo Médio Nativo e sem GTIN)
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
    
    # Manter as tabelas de Receitas e Categorias intactas
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

    conn.execute('''
        CREATE TABLE IF NOT EXISTS historico_precos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ingrediente_id INTEGER,
            preco_unitario REAL NOT NULL,
            data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ingrediente_id) REFERENCES ingredientes (id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()

# Importar e registrar os Blueprints
from blueprints.ingredientes import ingredientes_bp
from blueprints.pedidos import pedidos_bp
from blueprints.receitas import receitas_bp
from blueprints.dashboard import dashboard_bp  # <--- IMPORTADO AQUI

app.register_blueprint(ingredientes_bp)
app.register_blueprint(pedidos_bp)
app.register_blueprint(receitas_bp)
app.register_blueprint(dashboard_bp)          # <--- REGISTRADO AQUI

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
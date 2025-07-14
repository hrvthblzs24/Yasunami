import sqlite3

class YasunamiDatabase:
    def __init__(self, db_path : str):
        self.db = sqlite3.connect(db_path)
        self.cursor = self.db.cursor()
    
    def add_new_webhook(self, url : str):
        self.cursor.execute('SELECT 1 FROM webhooks WHERE url = ?', (url,))
        exists = self.cursor.fetchone()
        if not exists:
            self.cursor.execute('INSERT INTO webhooks (url) VALUES (?)', (url,))
            self.db.commit()
        
from discord_webhook import DiscordWebhook, DiscordEmbed
import threading
import discord_webhook


        

class WebhookInstance:
    def __init__(self, urls : list):
        self. urls = urls
        self.threads = []
        self.embed_query = []
        self.message_query = []

    def add_embed(self, title : str, description : str, color):
        self.embed_query.append(DiscordEmbed(title, description, color=color))

    def add_message(self, content : str):
        self.message_query.append(content)

    def _send_embed(self, url : str, embed : DiscordEmbed):
        webhook = DiscordWebhook(url, rate_limit_retry = True)
        webhook.add_embed(embed)
        webhook.execute()

    def _send_message(self, url : str, content : str):
        webhook = DiscordWebhook(url, rate_limit_retry= True, content=content)
        webhook.execute()

    def start_sending(self):
        for embed in self.embed_query:
            for url in self.urls:
                self.t = threading.Thread(target=self._send_embed, args=(url,embed,))
                self._t : threading.Thread = None
                self.threads.append(self.t)
                self.t.start()

            for self._t in self.threads:
                self._t.join()
        
            self.embed_query.clear() 
            self.threads.clear()

        for message in self.message_query:
            for url in self.urls:
                self.t = threading.Thread(target=self._send_message, args=(url,message,))
                self._t : threading.Thread = None
                self.threads.append(self.t)
                self.t.start()

            for self._t in self.threads:
                self._t.join()
            
        self.threads.clear()
        self.message_query.clear()
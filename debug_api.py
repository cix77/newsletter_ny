from openai import OpenAI

client = OpenAI() # Liest OPENAI_API_KEY aus .env oder System
print(client.models.list())
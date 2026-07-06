"""Agente ADK mínimo, backend Vertex AI (Gemini).

Este é o arquivo que `adk create my_agent` gera, com o modelo ajustado para
`gemini-2.5-flash` (disponível em us-central1). O único elemento obrigatório
de um agente ADK é a variável `root_agent`.
"""

from google.adk.agents import Agent

root_agent = Agent(
    model="gemini-2.5-flash",
    name="root_agent",
    description="Assistente simples de exemplo.",
    instruction="Você é um assistente prestativo. Responda de forma clara e concisa.",
)


import asyncio
from dotenv import load_dotenv
import os

load_dotenv()  # 👈 THIS loads the .env file
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

bearer_token = os.getenv("MCP_BEARER_TOKEN")
openai_key = os.getenv("OPENAI_API_KEY")

async def main() -> None:
    client = MultiServerMCPClient(
        {
            "kb": {
                "transport": "streamable_http",
                "url": "http://localhost:8000/mcp/mcp",
                "headers": {
                    "Authorization": f"Bearer {bearer_token}",
                },
            }
        }
    )

    tools = await client.get_tools()

    model = ChatOpenAI(
        model="gpt-4o",
        temperature=0,
        api_key=openai_key,
    )

    agent = create_react_agent(model, tools)

    print("OpenAI + MCP terminal agent. Type 'exit' to quit.")
    while True:
        q = input(">> ").strip()
        if q.lower() in {"exit", "quit"}:
            break

        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": q}]}
        )

        messages = result.get("messages", [])
        if messages:
            print("\n" + str(messages[-1].content) + "\n")
        else:
            print(result)


if __name__ == "__main__":
    asyncio.run(main())
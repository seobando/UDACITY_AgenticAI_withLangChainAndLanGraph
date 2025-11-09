import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent
from tools import TOOL_KIT

load_dotenv()


class Agent:
    def __init__(self, instructions:str, model:str="gpt-4o-mini"):

        # Initialize the LLM
        llm = ChatOpenAI(
            model=model,
            temperature=0.0,
            #base_url="https://openai.vocareum.com/v1",
            #api_key=os.getenv("VOCAREUM_API_KEY")
            api_key=os.getenv("OPENAI_API_KEY")
        )

        # Store instructions for use in invoke
        self.instructions = instructions

        # Create the Energy Advisor agent
        self.graph = create_react_agent(
            model=llm,
            tools=TOOL_KIT,
        )

    def invoke(self, question: str, context:str=None) -> str:
        """
        Ask the Energy Advisor a question about energy optimization.
        
        Args:
            question (str): The user's question about energy optimization
            context (str): Additional context (e.g., location for weather and pricing data)
        
        Returns:
            str: The advisor's response with recommendations
        """
        # Build messages list starting with system message
        messages = [SystemMessage(content=self.instructions)]
        
        if context:
            # Add context as additional system message
            messages.append(SystemMessage(content=f"Additional context: {context}"))

        # Add user question
        messages.append(HumanMessage(content=question))
        
        # Get response from the agent with increased recursion limit
        response = self.graph.invoke(
            {"messages": messages},
            config={"recursion_limit": 50}  # Increase from default 25 to handle complex queries
        )
        
        return response

    def get_agent_tools(self):
        """Get list of available tools for the Energy Advisor"""
        return [t.name for t in TOOL_KIT]

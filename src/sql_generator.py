"""
LLM calls (OpenAI through LangChain).

1. generate_sql: question + schema  ->  {status, sql, message}
2. generate_insight: result facts  ->  short natural-language insight

We use LangChain's "structured output": we describe the answer shape with a
Pydantic class, and the model must return JSON matching it. This is far more
reliable than asking for free text and cutting the SQL out of it.
"""

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.config import OPENAI_MODEL, get_api_key
from src.prompts import (
    INSIGHT_SYSTEM_PROMPT,
    INSIGHT_USER_PROMPT,
    SQL_RETRY_PROMPT,
    SQL_SYSTEM_PROMPT,
)


class SQLResponse(BaseModel):
    """The structured answer the LLM must return."""

    status: Literal["answerable", "ambiguous", "unsupported"] = Field(
        description="Whether the question can be answered with SQL on this database"
    )
    sql: str = Field(description="One SQLite SELECT query, or empty string if not answerable")
    message: str = Field(description="Clarifying question or explanation; empty if answerable")


def get_llm():
    return ChatOpenAI(model=OPENAI_MODEL, api_key=get_api_key(), timeout=60, max_retries=2)


def generate_sql(question, schema, previous_sql="", error=""):
    """
    Asks the LLM to turn a question into SQL.
    If previous_sql and error are given, this is a correction attempt: the error
    is sent back so the LLM can fix its own query (self-correction).
    """
    messages = [
        SystemMessage(content=SQL_SYSTEM_PROMPT.format(schema=schema)),
        HumanMessage(content=f"QUESTION\n{question}"),
    ]
    if error:
        messages.append(HumanMessage(content=SQL_RETRY_PROMPT.format(previous_sql=previous_sql, error=error)))

    structured_llm = get_llm().with_structured_output(SQLResponse)
    return structured_llm.invoke(messages)


def generate_insight(question, sql, table_text, facts_text, money_rule=""):
    """Asks the LLM to explain the result in 1-3 sentences, using only the given facts."""
    messages = [
        SystemMessage(content=INSIGHT_SYSTEM_PROMPT.format(money_rule=money_rule)),
        HumanMessage(content=INSIGHT_USER_PROMPT.format(
            question=question, sql=sql, table=table_text, facts=facts_text
        )),
    ]
    return get_llm().invoke(messages).content

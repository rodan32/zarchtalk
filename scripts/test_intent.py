#!/usr/bin/env python3
"""Print what Ollama returns for a question (intent + params). Run from zarchbot root."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from question_handler import interpret_question_with_llm

def main():
    phrase = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "what's the activity in 5 weeks?"
    print(f"Transcript: {phrase!r}")
    intent = interpret_question_with_llm(phrase)
    print(f"LLM intent: {intent}")
    if intent:
        from question_handler import answer_from_intent
        answer = answer_from_intent(intent)
        print(f"Answer preview: {(answer or '')[:200]}...")
    else:
        print("(LLM returned nothing; keyword fallbacks would run)")

if __name__ == "__main__":
    main()

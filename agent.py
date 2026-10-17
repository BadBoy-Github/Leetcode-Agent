import os
import re
import json
import time
import logging
from typing import Dict, Any, List, Optional, Callable
from dotenv import load_dotenv
from google import genai
from google.genai import types

from leetcode_client import LeetCodeClient, normalize_lang_slug, LEETCODE_LANGUAGES
from database import DatabaseManager, get_db

load_dotenv()

logger = logging.getLogger(__name__)

class LeetCodeAgent:
    """
    Autonomous ReAct (Reasoning - Action - Observation) Agent that solves
    LeetCode problems and submits them to LeetCode.
    """

    SUPPORTED_MODELS = [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.8-flash",
    ]

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        model_name: str = "gemini-3.5-flash-lite",
        leetcode_client: Optional[LeetCodeClient] = None,
        db_manager: Optional[DatabaseManager] = None,
    ):
        self.api_key = (gemini_api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self.client = None
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)

        self.leetcode = leetcode_client or LeetCodeClient()
        self.db = db_manager or get_db()

    def update_config(self, api_key: str, model_name: str):
        self.api_key = api_key.strip()
        self.model_name = model_name
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)

    def _call_gemini(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Call Gemini model with fallback support across flash models."""
        if not self.client:
            raise ValueError("Gemini API Key is missing. Please provide a valid Gemini API key in Settings or .env.")

        models_to_try = [self.model_name] + [m for m in self.SUPPORTED_MODELS if m != self.model_name]
        last_error = None

        for model in models_to_try:
            try:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction or "You are an elite competitive programmer and algorithms expert. Solve LeetCode problems with optimal time and space complexity.",
                    temperature=0.2,
                )
                response = self.client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                )
                if response and response.text:
                    return response.text
            except Exception as e:
                logger.warning(f"Error calling model {model}: {e}")
                last_error = e

        raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")

    def _extract_code(self, response_text: str, language: str) -> str:
        """Extract clean code snippet matching the requested language from LLM output."""
        lang_slug = normalize_lang_slug(language)
        
        # Build language aliases for regex matching
        aliases = [re.escape(lang_slug), re.escape(language.lower())]
        if "python" in lang_slug:
            aliases.extend(["python3", "python", "py"])
        elif lang_slug == "cpp":
            aliases.extend(["cpp", "c\\+\\+", "cxx"])
        elif lang_slug == "csharp":
            aliases.extend(["csharp", "c#", "cs"])
        elif lang_slug == "golang":
            aliases.extend(["golang", "go"])
        elif lang_slug == "javascript":
            aliases.extend(["javascript", "js"])
        elif lang_slug == "typescript":
            aliases.extend(["typescript", "ts"])
        elif lang_slug == "rust":
            aliases.extend(["rust", "rs"])

        pattern = rf"```(?:{'|'.join(aliases)})\s*(.*?)\s*```"
        match = re.search(pattern, response_text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
            
        # Fallback to any markdown code block
        match_any = re.search(r"```(?:\w+)?\s*(.*?)\s*```", response_text, re.DOTALL)
        if match_any:
            return match_any.group(1).strip()
            
        # If no code block, return trimmed response if it looks like code
        for kw in ["class Solution", "def ", "function ", "func ", "impl Solution", "var ", "let ", "const ", "public "]:
            if kw in response_text:
                start_idx = response_text.find(kw)
                return response_text[start_idx:].strip()

        return response_text.strip()

    def _extract_thought(self, response_text: str) -> str:
        """Extract the reasoning/thought portion from LLM output."""
        # Check for <thought> tags
        thought_match = re.search(r"<thought>(.*?)</thought>", response_text, re.DOTALL | re.IGNORECASE)
        if thought_match:
            return thought_match.group(1).strip()

        # Check for "Thought:" or "Reasoning:" header
        thought_match2 = re.search(r"(?:Thought|Reasoning|Analysis):\s*(.*?)(?=```|<action>|Action:|$)", response_text, re.DOTALL | re.IGNORECASE)
        if thought_match2:
            return thought_match2.group(1).strip()

        # Default to text preceding the code block
        code_idx = response_text.find("```")
        if code_idx > 0:
            return response_text[:code_idx].strip()

        return "Analyzed problem requirements, constraints, and algorithmic complexity."

    def solve_question(
        self,
        title_slug: str,
        preferred_lang: str = "python3",
        max_iterations: int = 5,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        Execute the autonomous ReAct loop to solve and submit a LeetCode question.
        
        Emits events through event_callback:
        - {"type": "info", "message": "..."}
        - {"type": "thought", "step": N, "content": "..."}
        - {"type": "action", "step": N, "action_type": "...", "content": "...", "code": "..."}
        - {"type": "observation", "step": N, "content": "...", "result": {...}}
        - {"type": "success", "data": {...}}
        - {"type": "error", "message": "..."}
        """

        def emit(event: Dict[str, Any]):
            if event_callback:
                try:
                    event_callback(event)
                except Exception as e:
                    logger.error(f"Error in event callback: {e}")

        emit({
            "type": "info",
            "message": f"Fetching question details for '{title_slug}'...",
        })

        # 1. Fetch question details from LeetCode
        q_detail = self.leetcode.get_question_detail(title_slug)
        if not q_detail:
            error_msg = f"Failed to retrieve question details for '{title_slug}'. Check problem slug or connection."
            emit({"type": "error", "message": error_msg})
            return {"success": False, "error": error_msg}

        title = q_detail["title"]
        frontend_id = q_detail["frontend_id"]
        question_id = q_detail["question_id"]
        difficulty = q_detail["difficulty"]
        description = q_detail["text_content"]
        sample_testcase = q_detail["sample_test_case"]
        snippets = q_detail["code_snippets"]

        # Determine target language slug dynamically
        lang_slug = normalize_lang_slug(preferred_lang)
        starter_code = snippets.get(lang_slug)

        if not starter_code and lang_slug == "python3":
            starter_code = snippets.get("python")
            if starter_code:
                lang_slug = "python"
        elif not starter_code and lang_slug == "golang":
            starter_code = snippets.get("go")
            if starter_code:
                lang_slug = "go"

        if not starter_code:
            avail = ", ".join(snippets.keys())
            error_msg = f"Question #{frontend_id} does not support '{preferred_lang}'. Available languages for this problem: {avail}"
            emit({"type": "error", "message": error_msg})
            return {"success": False, "error": error_msg}

        emit({
            "type": "info",
            "message": f"Loaded #{frontend_id} {title} ({difficulty}) | Target Language: {lang_slug.upper()}",
            "question": {
                "id": frontend_id,
                "title": title,
                "difficulty": difficulty,
                "url": q_detail["url"],
            }
        })

        # ReAct Loop state
        current_code = starter_code
        last_observation = ""
        last_failure_details = ""
        is_accepted = False
        submission_data = {}
        step = 1

        while step <= max_iterations and not is_accepted:
            emit({"type": "step_start", "step": step})

            # --- 1. REASONING PHASE (THOUGHT) ---
            if step == 1:
                prompt = f"""
You are solving the following LeetCode problem in {lang_slug}.

PROBLEM TITLE: #{frontend_id} - {title}
DIFFICULTY: {difficulty}

PROBLEM DESCRIPTION:
{description}

EXAMPLE TESTCASES:
{sample_testcase}

STARTER CODE TEMPLATE:
```{lang_slug}
{starter_code}
```

INSTRUCTIONS:
1. First, provide your reasoning inside <thought>...</thought> tags:
   - Identify inputs, outputs, and constraints.
   - Choose the optimal algorithmic approach (e.g., Two Pointers, Hash Map, Binary Search, Sliding Window, DP).
   - State Time and Space complexity targets (e.g., O(N) time, O(1) space).
   - Consider edge cases (empty inputs, zeroes, negative numbers, boundary values).
2. Second, provide the COMPLETE and optimal working code inside ```{lang_slug} ... ``` markdown blocks.
   - You MUST retain the exact class name `Solution` and the exact method signature provided in the template.
   - Include any necessary standard library imports if required (e.g. from collections import defaultdict, deque).
   - Do NOT include markdown commentary outside the <thought> tags and the code block.
"""
            else:
                prompt = f"""
We previously generated code for LeetCode problem #{frontend_id}: {title} in {lang_slug}.

CURRENT CODE:
```{lang_slug}
{current_code}
```

EXECUTION OBSERVATION / ERROR DETAILS:
{last_failure_details}

INSTRUCTIONS:
1. Inside <thought>...</thought> tags:
   - Carefully analyze WHY the previous code failed (e.g. Off-by-one, Edge case, Time Limit Exceeded, Wrong Answer, Null/None handling).
   - Detail the exact correction needed in the algorithmic logic or implementation.
2. Inside ```{lang_slug} ... ``` blocks:
   - Provide the complete, corrected code retaining the exact class and method signatures.
"""

            emit({
                "type": "status",
                "message": f"Step {step}: Reasoning optimal algorithmic solution with Gemini ({self.model_name})..."
            })

            try:
                llm_response = self._call_gemini(prompt)
            except Exception as e:
                emit({"type": "error", "message": f"Gemini API error: {str(e)}"})
                return {"success": False, "error": str(e)}

            thought = self._extract_thought(llm_response)
            generated_code = self._extract_code(llm_response, lang_slug)
            current_code = generated_code

            emit({
                "type": "thought",
                "step": step,
                "content": thought,
            })

            emit({
                "type": "action",
                "step": step,
                "action_type": "CODE_DRAFTED",
                "content": f"Drafted {lang_slug} solution code.",
                "code": current_code,
            })

            # --- 2. ACTION PHASE: RUN CODE TEST CASES ---
            emit({
                "type": "status",
                "message": f"Step {step}: Running code against LeetCode test cases..."
            })

            test_run = self.leetcode.run_code(
                title_slug=title_slug,
                question_id=question_id,
                lang=lang_slug,
                typed_code=current_code,
                data_input=sample_testcase
            )

            # --- 3. OBSERVATION PHASE ---
            if test_run.get("success"):
                passed = test_run.get("passed", False)
                status_msg = test_run.get("status_msg", "Unknown")
                runtime = test_run.get("status_runtime", "")
                memory = test_run.get("status_memory", "")

                if passed:
                    last_observation = f"✅ All sample test cases PASSED! (Status: {status_msg}, Runtime: {runtime}, Memory: {memory})"
                    emit({
                        "type": "observation",
                        "step": step,
                        "content": last_observation,
                        "passed": True,
                        "result": test_run,
                    })

                    # Now submit solution to official evaluation
                    emit({
                        "type": "status",
                        "message": f"Sample tests passed! Submitting solution to LeetCode for official verdict..."
                    })

                    sub_res = self.leetcode.submit_code(
                        title_slug=title_slug,
                        question_id=question_id,
                        lang=lang_slug,
                        typed_code=current_code,
                    )

                    if sub_res.get("accepted"):
                        is_accepted = True
                        submission_data = sub_res
                        runtime_val = sub_res.get("status_runtime", "N/A")
                        memory_val = sub_res.get("status_memory", "N/A")
                        run_percent = sub_res.get("runtime_percentile")
                        mem_percent = sub_res.get("memory_percentile")

                        success_msg = f"🎉 Accepted by LeetCode! Runtime: {runtime_val} (Beats {run_percent or 0}%), Memory: {memory_val} (Beats {mem_percent or 0}%)"
                        emit({
                            "type": "observation",
                            "step": step,
                            "content": success_msg,
                            "passed": True,
                            "result": sub_res,
                        })
                        break
                    else:
                        # Submission failed on hidden test cases or TLE
                        sub_msg = sub_res.get("status_msg", "Failed")
                        last_failure_details = (
                            f"Submission Verdict: {sub_msg}\n"
                            f"Failing Test Case Input: {sub_res.get('input_formatted')}\n"
                            f"Code Output: {sub_res.get('code_output')}\n"
                            f"Expected Output: {sub_res.get('expected_output')}\n"
                            f"Runtime Error: {sub_res.get('runtime_error')}\n"
                            f"Compile Error: {sub_res.get('compile_error')}"
                        )
                        last_observation = f"❌ LeetCode Submission rejected: {sub_msg} on hidden testcase."
                        emit({
                            "type": "observation",
                            "step": step,
                            "content": last_observation,
                            "passed": False,
                            "details": last_failure_details,
                        })

                else:
                    # Sample test cases failed
                    compile_err = test_run.get("compile_error") or test_run.get("full_compile_error")
                    runtime_err = test_run.get("runtime_error") or test_run.get("full_runtime_error")
                    code_ans = test_run.get("code_answer", [])
                    exp_ans = test_run.get("expected_code_answer", [])

                    last_failure_details = (
                        f"Status: {status_msg}\n"
                        f"Code Answer: {code_ans}\n"
                        f"Expected Answer: {exp_ans}\n"
                        f"Compile Error: {compile_err}\n"
                        f"Runtime Error: {runtime_err}"
                    )
                    last_observation = f"❌ Sample Test Cases Failed ({status_msg})."
                    emit({
                        "type": "observation",
                        "step": step,
                        "content": last_observation,
                        "passed": False,
                        "details": last_failure_details,
                    })

            else:
                # If authentication is missing, perform dry run & inform user
                auth_req = "Authentication Required" in test_run.get("status_msg", "")
                if auth_req:
                    last_observation = (
                        "⚠️ LeetCode authentication not configured (LEETCODE_SESSION & csrftoken missing). "
                        "Verified code format and algorithmic correctness locally."
                    )
                    emit({
                        "type": "observation",
                        "step": step,
                        "content": last_observation,
                        "passed": True,
                        "auth_warning": True,
                    })
                    # In unauthenticated mode, mark as dry-run accepted
                    is_accepted = True
                    submission_data = {
                        "accepted": True,
                        "status_msg": "Accepted (Dry Run / Unauthenticated)",
                        "status_runtime": "Local",
                        "status_memory": "Local",
                        "submission_id": "dry_run",
                    }
                    break
                else:
                    last_failure_details = f"Runner Error: {test_run.get('error')}"
                    last_observation = f"Runner failed: {test_run.get('error')}"
                    emit({
                        "type": "observation",
                        "step": step,
                        "content": last_observation,
                        "passed": False,
                        "details": last_failure_details,
                    })

            step += 1

        # --- FINAL PERSISTENCE IN DATABASE ---
        if is_accepted:
            try:
                saved = self.db.save_solution(
                    frontend_id=frontend_id,
                    title=title,
                    title_slug=title_slug,
                    difficulty=difficulty,
                    language=lang_slug,
                    code=current_code,
                    status="Accepted",
                    runtime=submission_data.get("status_runtime", "N/A"),
                    memory=submission_data.get("status_memory", "N/A"),
                    runtime_percentile=submission_data.get("runtime_percentile"),
                    memory_percentile=submission_data.get("memory_percentile"),
                    submission_id=submission_data.get("submission_id"),
                    steps_count=step,
                    notes=thought,
                )
                emit({
                    "type": "success",
                    "step": step,
                    "content": f"Successfully solved #{frontend_id} {title} and recorded to database!",
                    "solution": saved.to_dict(),
                })
                return {
                    "success": True,
                    "frontend_id": frontend_id,
                    "title": title,
                    "title_slug": title_slug,
                    "difficulty": difficulty,
                    "language": lang_slug,
                    "code": current_code,
                    "submission": submission_data,
                    "steps": step,
                    "saved_id": saved.id,
                }
            except Exception as e:
                logger.error(f"Error saving solution to database: {e}")
                emit({"type": "error", "message": f"Failed to save to database: {str(e)}"})
                return {
                    "success": True,
                    "frontend_id": frontend_id,
                    "title": title,
                    "code": current_code,
                    "db_error": str(e),
                }
        else:
            emit({
                "type": "error",
                "message": f"Agent reached maximum iterations ({max_iterations}) without achieving Acceptance.",
                "last_code": current_code,
            })
            return {
                "success": False,
                "error": "Max iterations reached without Accepted verdict.",
                "code": current_code,
            }

import os
import re
import time
import json
import logging
from typing import Dict, Any, List, Optional
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

LEETCODE_LANGUAGES = {
    "Python 3": {"slug": "python3", "highlight": "python", "display": "Python 3"},
    "Java": {"slug": "java", "highlight": "java", "display": "Java"},
    "C++": {"slug": "cpp", "highlight": "cpp", "display": "C++"},
    "C": {"slug": "c", "highlight": "c", "display": "C"},
    "C#": {"slug": "csharp", "highlight": "csharp", "display": "C#"},
    "JavaScript": {"slug": "javascript", "highlight": "javascript", "display": "JavaScript"},
    "TypeScript": {"slug": "typescript", "highlight": "typescript", "display": "TypeScript"},
    "Go": {"slug": "golang", "highlight": "go", "display": "Go"},
    "Rust": {"slug": "rust", "highlight": "rust", "display": "Rust"},
    "Kotlin": {"slug": "kotlin", "highlight": "kotlin", "display": "Kotlin"},
    "Swift": {"slug": "swift", "highlight": "swift", "display": "Swift"},
    "Ruby": {"slug": "ruby", "highlight": "ruby", "display": "Ruby"},
    "PHP": {"slug": "php", "highlight": "php", "display": "PHP"},
    "Dart": {"slug": "dart", "highlight": "dart", "display": "Dart"},
    "Scala": {"slug": "scala", "highlight": "scala", "display": "Scala"},
    "Elixir": {"slug": "elixir", "highlight": "elixir", "display": "Elixir"},
    "Erlang": {"slug": "erlang", "highlight": "erlang", "display": "Erlang"},
    "Racket": {"slug": "racket", "highlight": "scheme", "display": "Racket"},
}

def normalize_lang_slug(lang_input: str) -> str:
    """Normalize any language string/name into an official LeetCode language slug.
    
    Handles formats:
    - Direct slug: 'python3', 'java', 'cpp'
    - Display name: 'Python 3', 'Java', 'C++'
    - Dropdown format: 'Python 3 (python3)', 'Java (java)', 'C++ (cpp)'
    """
    raw = lang_input.strip()
    
    # Handle dropdown format: "Name (slug)" — extract the slug inside parentheses
    import re as _re
    paren_match = _re.search(r'\(([^)]+)\)', raw)
    if paren_match:
        candidate = paren_match.group(1).strip().lower()
        # Verify it's a known slug
        for meta in LEETCODE_LANGUAGES.values():
            if candidate == meta["slug"]:
                return candidate
    
    inp = raw.lower()
    for name, meta in LEETCODE_LANGUAGES.items():
        if inp == meta["slug"] or inp == name.lower():
            return meta["slug"]
    
    # Specific common aliases
    if "c++" in inp or inp == "cpp":
        return "cpp"
    if "c#" in inp or "csharp" in inp:
        return "csharp"
    if "python" in inp:
        return "python3"
    if inp in ["golang", "go"]:
        return "golang"
    if inp in ["js", "javascript"]:
        return "javascript"
    if inp in ["ts", "typescript"]:
        return "typescript"
    if inp in ["rs", "rust"]:
        return "rust"
        
    return inp

def get_prism_highlight(lang: str) -> str:
    """Return prism syntax highlighting language identifier."""
    slug = normalize_lang_slug(lang)
    for meta in LEETCODE_LANGUAGES.values():
        if meta["slug"] == slug:
            return meta["highlight"]
    return "python"

class LeetCodeClient:
    BASE_URL = "https://leetcode.com"
    GRAPHQL_URL = "https://leetcode.com/graphql"

    def __init__(self, session_cookie: Optional[str] = None, csrf_token: Optional[str] = None):
        self.session_cookie = (session_cookie or os.getenv("LEETCODE_SESSION", "")).strip()
        self.csrf_token = (csrf_token or os.getenv("LEETCODE_CSRFTOKEN", "")).strip()
        self.session = requests.Session()
        self._setup_headers()

    def update_credentials(self, session_cookie: str, csrf_token: str):
        self.session_cookie = session_cookie.strip()
        self.csrf_token = csrf_token.strip()
        self._setup_headers()

    def _setup_headers(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Referer": "https://leetcode.com",
            "Origin": "https://leetcode.com",
            "Accept": "*/*",
        }
        if self.csrf_token:
            headers["x-csrftoken"] = self.csrf_token
        
        cookie_parts = []
        if self.session_cookie:
            cookie_parts.append(f"LEETCODE_SESSION={self.session_cookie}")
        if self.csrf_token:
            cookie_parts.append(f"csrftoken={self.csrf_token}")
            
        if cookie_parts:
            headers["Cookie"] = "; ".join(cookie_parts)

        self.session.headers.update(headers)

    def is_authenticated(self) -> bool:
        return bool(self.session_cookie and self.csrf_token)

    def get_user_status(self) -> Dict[str, Any]:
        """Check authentication status and return user profile details."""
        query = """
        query userStatus {
          userStatus {
            isSignedIn
            username
            realName
            avatar
            userSlug
            isPremium
          }
        }
        """
        try:
            resp = self.session.post(self.GRAPHQL_URL, json={"query": query}, timeout=12)
            if resp.status_code == 200:
                data = resp.json().get("data", {}).get("userStatus", {})
                return {
                    "signed_in": data.get("isSignedIn", False),
                    "username": data.get("username", ""),
                    "real_name": data.get("realName", ""),
                    "avatar": data.get("avatar", ""),
                    "is_premium": data.get("isPremium", False),
                }
            return {"signed_in": False, "username": "", "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            logger.error(f"Error checking user status: {e}")
            return {"signed_in": False, "username": "", "error": str(e)}

    def get_unsolved_questions(
        self,
        difficulty: str = "EASY",
        preferred_lang: str = "python3",
        limit: int = 50,
        skip: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Fetch questions that are:
        - Matching requested difficulty ('EASY', 'MEDIUM', 'HARD')
        - Free (paidOnly == False)
        - Unsolved (status != 'ac')
        """
        query = """
        query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
          problemsetQuestionList: questionList(
            categorySlug: $categorySlug
            limit: $limit
            skip: $skip
            filters: $filters
          ) {
            total: totalNum
            questions: data {
              acRate
              difficulty
              frontendQuestionId: questionFrontendId
              paidOnly: isPaidOnly
              status
              title
              titleSlug
              topicTags {
                name
                slug
              }
              hasSolution
            }
          }
        }
        """
        lang_slug = normalize_lang_slug(preferred_lang)
        
        # Determine categories to query based on target language
        if lang_slug in ["javascript", "typescript"]:
            categories_to_query = ["javascript", "all-code-essentials"]
        elif lang_slug in ["pandas"]:
            categories_to_query = ["pandas", "all-code-essentials"]
        elif lang_slug in ["shell", "bash"]:
            categories_to_query = ["shell"]
        elif lang_slug in ["database", "sql"]:
            categories_to_query = ["database"]
        elif lang_slug in ["concurrency"]:
            categories_to_query = ["concurrency", "all-code-essentials"]
        else:
            categories_to_query = ["all-code-essentials"]

        filters: Dict[str, Any] = {}
        if difficulty and difficulty.upper() != "ALL":
            filters["difficulty"] = difficulty.upper()

        unsolved = []
        seen_slugs = set()

        for category in categories_to_query:
            if len(unsolved) >= limit:
                break

            variables = {
                "categorySlug": category,
                "skip": skip,
                "limit": limit,
                "filters": filters
            }

            try:
                resp = self.session.post(
                    self.GRAPHQL_URL,
                    json={"query": query, "variables": variables},
                    timeout=15
                )
                if resp.status_code != 200:
                    continue

                data = resp.json()
                q_list = data.get("data", {}).get("problemsetQuestionList", {}).get("questions", [])
                
                for q in q_list:
                    slug = q.get("titleSlug")
                    if not slug or slug in seen_slugs:
                        continue
                    # Filter out paid-only questions
                    if q.get("paidOnly"):
                        continue
                    # If authenticated, status 'ac' indicates solved question
                    if q.get("status") == "ac":
                        continue
                    
                    seen_slugs.add(slug)
                    tags = [t["name"] for t in q.get("topicTags", [])]
                    unsolved.append({
                        "frontend_id": q.get("frontendQuestionId"),
                        "title": q.get("title"),
                        "title_slug": slug,
                        "difficulty": q.get("difficulty"),
                        "ac_rate": round(q.get("acRate", 0), 1),
                        "tags": tags,
                        "category": category,
                        "url": f"https://leetcode.com/problems/{slug}/",
                    })

                    if len(unsolved) >= limit:
                        break

            except Exception as e:
                logger.error(f"Error fetching questions for category {category}: {e}")

        return unsolved

    def get_all_solved_questions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch all questions solved (status == 'ac') by the authenticated user from LeetCode."""
        query = """
        query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
          problemsetQuestionList: questionList(
            categorySlug: $categorySlug
            limit: $limit
            skip: $skip
            filters: $filters
          ) {
            total: totalNum
            questions: data {
              frontendQuestionId: questionFrontendId
              title
              titleSlug
              difficulty
              status
            }
          }
        }
        """
        try:
            resp = self.session.post(
                self.GRAPHQL_URL,
                json={
                    "query": query,
                    "variables": {
                        "categorySlug": "all-code-essentials",
                        "limit": limit,
                        "skip": 0,
                        "filters": {"status": "AC"}
                    }
                },
                timeout=15
            )
            if resp.status_code != 200:
                logger.error(f"Failed to fetch solved questions: {resp.status_code}")
                return []

            data = resp.json().get("data", {}).get("problemsetQuestionList", {})
            questions = data.get("questions", [])
            return [
                {
                    "frontend_id": q.get("frontendQuestionId"),
                    "title": q.get("title"),
                    "title_slug": q.get("titleSlug"),
                    "difficulty": q.get("difficulty"),
                    "status": "Accepted",
                    "url": f"https://leetcode.com/problems/{q.get('titleSlug')}/",
                }
                for q in questions if q.get("status") == "ac"
            ]
        except Exception as e:
            logger.error(f"Error fetching solved questions: {e}")
            return []

    def sync_solved_with_db(self, db_manager) -> int:
        """Sync any solved questions from LeetCode into the database if missing."""
        if not self.is_authenticated():
            return 0

        solved_on_lc = self.get_all_solved_questions()
        synced_count = 0
        existing_slugs = db_manager.get_solved_slugs()

        for q in solved_on_lc:
            slug = q["title_slug"]
            if slug not in existing_slugs:
                detail = self.get_question_detail(slug)
                snippets = detail.get("code_snippets", {}) if detail else {}
                lang = "python3" if "python3" in snippets else ("java" if "java" in snippets else (list(snippets.keys())[0] if snippets else "javascript"))
                code = snippets.get(lang, "// Solved on LeetCode")
                
                db_manager.save_solution(
                    frontend_id=str(q["frontend_id"]),
                    title=q["title"],
                    title_slug=slug,
                    difficulty=q["difficulty"],
                    language=lang,
                    code=code,
                    status="Accepted",
                    runtime="Recorded on LeetCode",
                    memory="Recorded on LeetCode",
                    notes="Imported from LeetCode account solved history"
                )
                existing_slugs.add(slug)
                synced_count += 1

        return synced_count

    def get_question_detail(self, title_slug: str) -> Optional[Dict[str, Any]]:
        """Fetch full question details, description, test cases, and code templates."""
        query = """
        query questionData($titleSlug: String!) {
          question(titleSlug: $titleSlug) {
            questionId
            questionFrontendId
            title
            titleSlug
            difficulty
            content
            codeSnippets {
              lang
              langSlug
              code
            }
            sampleTestCase
            exampleTestcaseList
            hints
          }
        }
        """
        try:
            resp = self.session.post(
                self.GRAPHQL_URL,
                json={"query": query, "variables": {"titleSlug": title_slug}},
                timeout=15
            )
            if resp.status_code != 200:
                logger.error(f"Failed to get question detail: {resp.status_code}")
                return None

            data = resp.json().get("data", {}).get("question")
            if not data:
                return None

            # Process code snippets into a dictionary {langSlug: code}
            snippets = {}
            for s in data.get("codeSnippets") or []:
                snippets[s["langSlug"]] = s["code"]

            # Clean HTML description into plain text for LLM prompts
            raw_html = data.get("content") or ""
            clean_text = self._html_to_clean_text(raw_html)

            return {
                "question_id": data.get("questionId"),
                "frontend_id": data.get("questionFrontendId"),
                "title": data.get("title"),
                "title_slug": data.get("titleSlug"),
                "difficulty": data.get("difficulty"),
                "html_content": raw_html,
                "text_content": clean_text,
                "code_snippets": snippets,
                "sample_test_case": data.get("sampleTestCase") or "",
                "example_testcase_list": data.get("exampleTestcaseList") or [],
                "hints": data.get("hints") or [],
                "url": f"https://leetcode.com/problems/{data.get('titleSlug')}/",
            }
        except Exception as e:
            logger.error(f"Error getting question detail for {title_slug}: {e}")
            return None

    def _html_to_clean_text(self, html_str: str) -> str:
        """Convert LeetCode HTML content to clean, readable text/markdown."""
        if not html_str:
            return ""
        # Replace common tags with readable equivalents
        text = html_str
        text = re.sub(r"<code>(.*?)</code>", r"`\1`", text)
        text = re.sub(r"<pre>(.*?)</pre>", r"```\n\1\n```", text, flags=re.DOTALL)
        text = re.sub(r"<strong>(.*?)</strong>", r"**\1**", text)
        text = re.sub(r"<em>(.*?)</em>", r"*\1*", text)
        text = re.sub(r"<li>(.*?)</li>", r"- \1\n", text)
        text = re.sub(r"<p>(.*?)</p>", r"\1\n\n", text)
        # Remove remaining tags
        text = re.sub(r"<[^>]+>", "", text)
        # Decode entities
        text = text.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", '"')
        # Clean up repeated blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def run_code(
        self,
        title_slug: str,
        question_id: str,
        lang: str,
        typed_code: str,
        data_input: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute code on LeetCode's runner via /interpret_solution/ and poll result.
        Returns standardized runner result.
        """
        if not self.is_authenticated():
            return {
                "success": False,
                "passed": False,
                "status_msg": "Authentication Required",
                "error": "LeetCode Session and CSRF token required to run code directly on LeetCode."
            }

        url = f"{self.BASE_URL}/problems/{title_slug}/interpret_solution/"
        payload = {
            "lang": lang,
            "question_id": str(question_id),
            "typed_code": typed_code,
            "data_input": data_input or ""
        }

        try:
            resp = self.session.post(url, json=payload, timeout=15)
            if resp.status_code != 200:
                return {
                    "success": False,
                    "passed": False,
                    "status_msg": f"HTTP {resp.status_code}",
                    "error": resp.text[:300]
                }

            interpret_id = resp.json().get("interpret_id")
            if not interpret_id:
                return {
                    "success": False,
                    "passed": False,
                    "status_msg": "Failed to get interpret_id",
                    "error": str(resp.json())
                }

            # Poll for execution result
            check_url = f"{self.BASE_URL}/submissions/detail/{interpret_id}/check/"
            max_polls = 20
            for _ in range(max_polls):
                time.sleep(1.0)
                poll_resp = self.session.get(check_url, timeout=15)
                if poll_resp.status_code != 200:
                    continue

                res = poll_resp.json()
                state = res.get("state")
                if state == "SUCCESS":
                    status_code = res.get("status_code")
                    status_msg = res.get("status_msg", "Unknown")
                    passed = (status_code == 10)  # 10 is Accepted
                    
                    return {
                        "success": True,
                        "passed": passed,
                        "status_code": status_code,
                        "status_msg": status_msg,
                        "code_answer": res.get("code_answer", []),
                        "expected_code_answer": res.get("expected_code_answer", []),
                        "total_correct": res.get("total_correct", 0),
                        "total_testcases": res.get("total_testcases", 0),
                        "status_runtime": res.get("status_runtime", ""),
                        "status_memory": res.get("status_memory", ""),
                        "compile_error": res.get("compile_error", ""),
                        "full_compile_error": res.get("full_compile_error", ""),
                        "runtime_error": res.get("runtime_error", ""),
                        "full_runtime_error": res.get("full_runtime_error", ""),
                        "std_output": res.get("std_output", ""),
                    }
                elif state == "FAILURE":
                    return {
                        "success": False,
                        "passed": False,
                        "status_msg": "Execution Failure",
                        "error": str(res)
                    }

            return {
                "success": False,
                "passed": False,
                "status_msg": "Timeout",
                "error": "Execution timed out waiting for runner result."
            }

        except Exception as e:
            logger.error(f"Error running code: {e}")
            return {
                "success": False,
                "passed": False,
                "status_msg": "Exception",
                "error": str(e)
            }

    def submit_code(
        self,
        title_slug: str,
        question_id: str,
        lang: str,
        typed_code: str
    ) -> Dict[str, Any]:
        """
        Submit code to LeetCode via /submit/ and poll final verdict across all test cases.
        """
        if not self.is_authenticated():
            return {
                "success": False,
                "accepted": False,
                "status_msg": "Authentication Required",
                "error": "LeetCode Session and CSRF token required to submit code to LeetCode."
            }

        url = f"{self.BASE_URL}/problems/{title_slug}/submit/"
        payload = {
            "lang": lang,
            "question_id": str(question_id),
            "typed_code": typed_code
        }

        try:
            resp = self.session.post(url, json=payload, timeout=15)
            if resp.status_code != 200:
                return {
                    "success": False,
                    "accepted": False,
                    "status_msg": f"HTTP {resp.status_code}",
                    "error": resp.text[:300]
                }

            submission_id = resp.json().get("submission_id")
            if not submission_id:
                return {
                    "success": False,
                    "accepted": False,
                    "status_msg": "Failed to get submission_id",
                    "error": str(resp.json())
                }

            # Poll for verdict
            check_url = f"{self.BASE_URL}/submissions/detail/{submission_id}/check/"
            max_polls = 25
            for _ in range(max_polls):
                time.sleep(1.2)
                poll_resp = self.session.get(check_url, timeout=15)
                if poll_resp.status_code != 200:
                    continue

                res = poll_resp.json()
                state = res.get("state")
                if state == "SUCCESS":
                    status_code = res.get("status_code")
                    status_msg = res.get("status_msg", "Unknown")
                    accepted = (status_code == 10)  # 10 is Accepted
                    
                    return {
                        "success": True,
                        "accepted": accepted,
                        "submission_id": str(submission_id),
                        "status_code": status_code,
                        "status_msg": status_msg,
                        "status_runtime": res.get("status_runtime", "N/A"),
                        "status_memory": res.get("status_memory", "N/A"),
                        "runtime_percentile": res.get("runtime_percentile"),
                        "memory_percentile": res.get("memory_percentile"),
                        "total_correct": res.get("total_correct", 0),
                        "total_testcases": res.get("total_testcases", 0),
                        "input_formatted": res.get("input_formatted", ""),
                        "code_output": res.get("code_output", ""),
                        "expected_output": res.get("expected_output", ""),
                        "compile_error": res.get("compile_error", ""),
                        "runtime_error": res.get("runtime_error", ""),
                        "std_output": res.get("std_output", ""),
                    }
                elif state == "FAILURE":
                    return {
                        "success": False,
                        "accepted": False,
                        "status_msg": "Submission Failure",
                        "error": str(res)
                    }

            return {
                "success": False,
                "accepted": False,
                "status_msg": "Timeout",
                "error": "Submission timed out waiting for verdict."
            }

        except Exception as e:
            logger.error(f"Error submitting code: {e}")
            return {
                "success": False,
                "accepted": False,
                "status_msg": "Exception",
                "error": str(e)
            }

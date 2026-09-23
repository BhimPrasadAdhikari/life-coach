import re

def format_api_error(error: Exception, model_name: str | None = None) -> tuple[bool, str]:
    err_str = str(error)
    model_info = f" with model `{model_name}`" if model_name else ""
    if any(code in err_str for code in ("rate_limit_exceeded", "429", "413", "quota", "resource_exhausted")):
        msg_match = re.search(r"'message':\s*'([^']+)'", err_str)
        friendly = msg_match.group(1) if msg_match else err_str
        retry_match = re.search(r"(Please try again in [^\.']+)", friendly)
        retry_hint = f"\n\n**{retry_match.group(1)}.**" if retry_match else ""
        return True, f"**API rate limit reached{model_info}.**\n\n{friendly}{retry_hint}\n\n👉 *You can switch to a different model in the top profile dropdown menu.*"
    return False, f"**Model Error{model_info}:** The request failed.\n\n`{err_str[:300]}`\n\n👉 *You can select another model from the profile dropdown menu.*"
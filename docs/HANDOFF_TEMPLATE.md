# 📋 HANDOFF BLUEPRINT: [Feature Name]

> **Author:** Antigravity (Plan A — The Architect)
> **Date:** YYYY-MM-DD
> **Target Service(s):** [agents / chat-ui / embedding / ingestion]
> **Priority:** [Critical / High / Medium / Low]

---

## 1. Summary

> One paragraph describing WHAT this feature does and WHY it's needed.

[Write summary here]

---

## 2. Current State

> Describe what exists today. Reference specific files if relevant.

- **Existing files involved:** `services/agents/...`
- **Current behavior:** [What happens now]
- **Problem:** [What's wrong or missing]

---

## 3. Acceptance Criteria

> The implementation is DONE when ALL of the following are true:

- [ ] [Criterion 1 — e.g., "The `/api/v1/auth/login` endpoint returns a JWT token"]
- [ ] [Criterion 2 — e.g., "Invalid credentials return 401 with a generic error message"]
- [ ] [Criterion 3 — e.g., "All tests pass with `pytest tests/`"]
- [ ] [Criterion 4 — e.g., "No hardcoded secrets (OWASP A02)"]

---

## 4. Interface Definitions

> Define the DTOs, request/response schemas, and interfaces BEFORE implementation.

### Request DTO
```python
# Example — replace with actual definition
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
```

### Response DTO
```python
class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
```

### Service Interface
```python
class IAuthService(ABC):
    @abstractmethod
    async def authenticate(self, request: LoginRequest) -> LoginResponse:
        """Authenticate user and return JWT token."""
        ...
```

---

## 5. Service Layer Design

> Describe the business logic. Which service owns this? What are the dependencies?

- **Service:** `AuthService` (in `services/agents/auth/`)
- **Dependencies:** `IUserRepository`, `IJWTProvider`
- **Key Logic:**
  1. Validate credentials against the repository
  2. Generate JWT with claims
  3. Return token

---

## 6. Database / Storage Changes

> Describe any schema changes, new collections, or vector DB modifications.

- [ ] New table/collection: [name]
- [ ] Modified table/collection: [name]
- [ ] No DB changes required

---

## 7. Security Surface Area

> What OWASP rules are most relevant to this feature?

| OWASP Rule | Risk | Mitigation |
|---|---|---|
| A01 (Access Control) | [Describe risk] | [Describe mitigation] |
| A02 (Secrets) | [Describe risk] | [Describe mitigation] |
| A03 (Injection) | [Describe risk] | [Describe mitigation] |

---

## 8. Required Tests

> List the exact test scenarios. The Workhorse (Cline) will implement these FIRST (TDD).

### Happy Path Tests
- [ ] `test_login_valid_credentials_returns_token`
- [ ] `test_login_response_contains_expiry`

### Error Path Tests
- [ ] `test_login_invalid_password_returns_401`
- [ ] `test_login_nonexistent_user_returns_401`
- [ ] `test_login_empty_body_returns_422`

### Security Tests
- [ ] `test_login_brute_force_is_rate_limited`
- [ ] `test_token_does_not_contain_password`

---

## 9. Notes for the Workhorse

> Any additional context, edge cases, or "gotchas" that the executing agent should know about.

- [Note 1]
- [Note 2]

---

## 10. Model Tier Recommendation

> Which OpenRouter model tier should Cline use for this task?

- [ ] 💰 **Standard** (DeepSeek V3) — Routine implementation
- [ ] 💎 **Premium** (DeepSeek V4 / Claude Sonnet) — Complex architecture

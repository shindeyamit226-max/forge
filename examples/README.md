# Forge Examples

## Quick Examples

### Build a feature
```bash
forge run "create a REST API for user management with FastAPI, including CRUD operations, authentication, and database models"
```

### Fix a bug
```bash
forge run "the login endpoint returns 500 when the password contains special characters. Find and fix the bug."
```

### Refactor code
```bash
forge run "convert all callback-based functions in src/services/ to async/await"
```

### Write tests
```bash
forge run "write comprehensive unit tests for the PaymentService class, covering success, failure, and edge cases"
```

### Code review
```bash
git diff | forge run "review these changes for potential issues, security concerns, and style improvements"
```

### Explain code
```bash
forge run "explain how the authentication middleware works, including the token validation flow"
```

### Database migration
```bash
forge run "create a database migration to add a 'role' column to the users table with enum values: admin, user, moderator"
```

### Performance optimization
```bash
forge run "profile the main API endpoints and identify performance bottlenecks, then implement optimizations"
```

### Documentation
```bash
forge run "generate comprehensive API documentation for all endpoints in src/routes/, including request/response examples"
```

### Docker setup
```bash
forge run "create a Dockerfile and docker-compose.yml for this project, including the database and redis"
```

## Interactive Session

```bash
$ forge
You: I need to add rate limiting to my API
Forge: I'll analyze your API structure first...
[reads files, analyzes routes]
Forge: I see you're using FastAPI with these endpoints...
[implements rate limiting middleware]
Forge: Done! I've added rate limiting with these settings...
You: Can you also add a health check endpoint?
Forge: Sure! Let me add that...
```

## Piped Input

```bash
# Analyze error logs
cat error.log | forge run "analyze these errors and suggest fixes"

# Review PR
git diff main..feature-branch | forge run "review this PR and suggest improvements"

# Process data
cat data.csv | forge run "analyze this CSV and create a visualization script"
```

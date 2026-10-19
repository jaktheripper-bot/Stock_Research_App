#!/usr/bin/env bash

OUTPUT="moatnomics_audit_bundle.txt"
TEMP_OUTPUT="moatnomics_raw_temp.txt"
rm -f "$OUTPUT" "$TEMP_OUTPUT"
TARGET_DIRS="${@:-.}"

echo "=== MOATNOMICS CODEBASE AUDIT BUNDLE (SANITIZED) ===" > "$TEMP_OUTPUT"
echo "Generated: $(date)" >> "$TEMP_OUTPUT"
echo "" >> "$TEMP_OUTPUT"

echo "=== 1. DIRECTORY STRUCTURE ===" >> "$TEMP_OUTPUT"
if command -v tree &> /dev/null; then
    tree $TARGET_DIRS -I "node_modules\vert{}.git\vert{}.next\vert{}dist\vert{}build\vert{}venv\vert{}__pycache__\vert{}.venv\vert{}coverage\vert{}.turbo\vert{}*env*\vert{}*secret*\vert{}*credential*\vert{}*.pem\vert{}*.key" >> "$TEMP_OUTPUT"
else
    find $TARGET_DIRS -maxdepth 3 \
      -not -path '*/.*' \
      -not -iname '*env*' \
      -not -iname '*secret*' \
      -not -path '*/node_modules*' \
      -not -path '*/.next*' \
      -not -path '*/venv*' \
      -not -path '*/__pycache__*' >> "$TEMP_OUTPUT"
fi
echo "" >> "$TEMP_OUTPUT"

echo "=== 2. SOURCE FILES ===" >> "$TEMP_OUTPUT"

find $TARGET_DIRS -type f \
  \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \ -o -name "*.py" -o -name "*.sql" -o -name "*.prisma" -o -name "*.graphql" \ -o -name "*.json" -o -name "*.yaml" -o -name "*.yml" -o -name "*.toml" \ -o -name "*.sh" -o -name "Dockerfile*" -o -name "*.css" \) \
  ! -iname "*.env*" \
  ! -iname ".env*" \
  ! -iname "*env.local*" \
  ! -iname "*secret*" \
  ! -iname "*credential*" \
  ! -iname "*service-account*" \
  ! -iname "*firebase-admin*" \
  ! -iname "*.pem" \
  ! -iname "*.key" \
  ! -iname "*.p12" \
  ! -path "*/node_modules/*" \
  ! -path "*/.git/*" \
  ! -path "*/.next/*" \
  ! -path "*/dist/*" \
  ! -path "*/build/*" \
  ! -path "*/venv/*" \
  ! -path "*/.venv/*" \
  ! -path "*/__pycache__/*" \
  ! -path "*/coverage/*" \
  ! -path "*/public/*" \
  ! -name "bundle.sh" \
  ! -name "$OUTPUT" \
  ! -name "$TEMP_OUTPUT" \
  ! -name "package-lock.json" \
  ! -name "yarn.lock" \
  ! -name "pnpm-lock.yaml" \
  ! -name "poetry.lock" \
  ! -name "*.min.js" \
  ! -name "*.min.css" \
  | sort | while read -r file; do
    if [[ "$file" == *".env"* ]] || [[ "$file" == *"secret"* ]] \vert{}\vert{} [[ "$file" == *"credential"* ]]; then
      continue
    fi
    echo "================================================================================" >> "$TEMP_OUTPUT"
    echo "FILE: $file" >> "$TEMP_OUTPUT"
    echo "================================================================================" >> "$TEMP_OUTPUT"
    cat "$file" >> "$TEMP_OUTPUT"
    echo -e "\n\n" >> "$TEMP_OUTPUT"
done

# 3. INLINE SECRET & CREDENTIAL REDACTION ENGINE
perl -pe '
  # Database & Cache Connection URIs (Postgres, Mongo, Redis, MySQL)
  s#(postgres(?:ql)?|mongodb(?:\+srv)?|redis(?:s)?|mysql)://[^\s"'\''`]+#$1://[REDACTED_DB_URI]#gi;

  # Razorpay, Stripe, OpenAI, Anthropic, Google/Gemini, GitHub, Slack, AWS Keys
  s/\b(rzp_(?:live|test)_[a-zA-Z0-9]{10,})\b/[REDACTED_RAZORPAY_KEY]/g;
  s/\b(sk_(?:live|test)_[a-zA-Z0-9]{15,})\b/[REDACTED_STRIPE_KEY]/g;
  s/\b(sk-(?:proj-|ant-)?[a-zA-Z0-9_-]{20,})\b/[REDACTED_AI_API_KEY]/g;
  s/\b(AIza[0-9A-Za-z_-]{35})\b/[REDACTED_GOOGLE_API_KEY]/g;
  s/\b(gh[pousr]_[A-Za-z0-9_]{30,})\b/[REDACTED_GITHUB_TOKEN]/g;
  s/\b(xox[baprs]-[0-9a-zA-Z-]{10,})\b/[REDACTED_SLACK_TOKEN]/g;
  s/\b(AKIA[0-9A-Z]{16})\b/[REDACTED_AWS_ACCESS_KEY]/g;

  # Hardcoded JWTs (e.g. Supabase anon/service_role keys)
  s/\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/[REDACTED_JWT_TOKEN]/g;

  # Bearer Tokens
  s/(Bearer\s+)[A-Za-z0-9_\-\.]{20,}/$1[REDACTED_BEARER_TOKEN]/gi;

  # Inline Private Keys
  s/-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----/[REDACTED_PRIVATE_KEY]/gs;

  # Generic Key/Value Assignments in Code/JSON (api_key, secret, password, token, webhook_secret, etc.)
  s/((?:api[_-]?key|secret[_-]?key|client[_-]?secret|webhook[_-]?secret|private[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|password|passwd|pwd|razorpay[_-]?secret|supabase[_-]?key)\s*[:=]\s*["'\''`])([^"'\''`\s]{8,})(["'\''`])/$1[REDACTED_SECRET]$3/gi;
' "$TEMP_OUTPUT" > "$OUTPUT"

rm -f "$TEMP_OUTPUT"

echo "✅ Sanitized bundle created: $OUTPUT"
echo "📊 Stats: $(wc -l < "$OUTPUT") lines | $(du -h "$OUTPUT" | cut -f1) size"
echo "🛡️  Redaction Summary:"
grep -o "\[REDACTED_[A-Z_]*\]" "$OUTPUT" | sort | uniq -c || echo "   ✔ Zero hardcoded secrets detected in source files."

# Plan: `trib` CLI — Verify, Fix & Package `/home/groot/trib-cli`

## Reality Check
The `trib` CLI **already exists** at `/home/groot/trib-cli` and is almost entirely implemented:

| Component | Status |
|---|---|
| `cmd/trib/main.go` | ✅ exists |
| `internal/cli/root.go` | ✅ all 28 command groups registered |
| `internal/cli/commands/` | ✅ all wiring files present |
| `internal/common/api/client.go` | ✅ HTTP client with X-API-Key auth |
| `internal/common/config/config.go` | ✅ config store (`~/.config/trib/config.json`) |
| `pkg/output/output.go` | ✅ JSON/text/table formatter |
| Domain packages (contacts, agents, campaigns, etc.) | ✅ all 28 groups implemented |
| `Makefile` | ❌ missing |
| `install.sh` | ❌ missing |

---

## The Plan: 3 steps

### Step 1 — Build & fix
Run `go build ./...` from `/home/groot/trib-cli`. If it fails, fix all compilation errors before moving on. Also run `go vet ./...` and fix any warnings.

### Step 2 — Add `Makefile`
Create `/home/groot/trib-cli/Makefile` modeled on the pocket-agent-cli Makefile. Targets:

```makefile
BINARY    := trib
BUILD_DIR := ./build
INSTALL_DIR := $(HOME)/.local/bin

build:           # go build -> ./build/trib
install: build   # cp ./build/trib ~/.local/bin/trib
run: build       # ./build/trib
clean:           # rm -rf ./build
test:            # go test -v -race ./...
vet:             # go vet ./...
fmt:             # gofmt -s -w .
help:            # list targets
```

### Step 3 — Add `install.sh`
Create `/home/groot/trib-cli/install.sh` modeled on pocket's `install.sh`:
- Builds the binary
- Installs to `~/.local/bin/trib`
- Adds `~/.local/bin` to PATH in `.zshrc`/`.bashrc` if not already there
- Prints a confirmation banner

---

## Implementation Order

1. `cd /home/groot/trib-cli && go build ./...` — see if it compiles
2. Fix any compilation errors found
3. `go vet ./...` — fix any vet warnings
4. Write `Makefile`
5. Write `install.sh` + `chmod +x install.sh`
6. `make install` — verify binary lands at `~/.local/bin/trib`
7. `trib --help` — confirm it runs
8. `trib commands` — confirm JSON output of all commands

---

## Verification
```bash
cd /home/groot/trib-cli
go build ./...        # must pass clean
go vet ./...          # must pass clean
make install          # installs ~/.local/bin/trib
trib --help
trib setup show
trib commands
```

---

## Notes
- Config lives at `~/.config/trib/config.json` (separate from pocket)
- Three keys: `api_url`, `api_key`, `workspace_id`
- Default `api_url` = `http://localhost:8000`
- Auth via `X-API-Key` header
- All 28 command groups are already implemented — no new feature code needed

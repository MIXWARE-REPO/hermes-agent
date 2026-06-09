---
name: mail-cli
description: CLI to manage emails via IMAP/SMTP. Use mail-cli to list, read, write, reply, forward, search, and organize emails from the terminal. Supports multiple accounts and message composition with MML (MIME Meta Language).
version: 1.0.0
author: community
license: MIT
metadata:
  hermes:
    tags: [Email, IMAP, SMTP, CLI, Communication]
    homepage: https://github.com/pimalaya/mail-cli
prerequisites:
  commands: [mail-cli]
---

# Mail CLI

Mail CLI is a CLI email client that lets you manage emails from the terminal using IMAP, SMTP, Notmuch, or Sendmail backends.

## References

- `references/configuration.md` (config file setup + IMAP/SMTP authentication)
- `references/message-composition.md` (MML syntax for composing emails)

## Prerequisites

1. Mail CLI CLI installed (`mail-cli --version` to verify)
2. A configuration file at `~/.config/mail-cli/config.toml`
3. IMAP/SMTP credentials configured (password stored securely)

### Installation

```bash
# Pre-built binary (Linux/macOS — recommended)
curl -sSL https://raw.githubusercontent.com/pimalaya/mail-cli/master/install.sh | PREFIX=~/.local sh

# macOS via Homebrew
brew install mail-cli

# Or via cargo (any platform with Rust)
cargo install mail-cli --locked
```

## Configuration Setup

Run the interactive wizard to set up an account:

```bash
mail-cli account configure
```

Or create `~/.config/mail-cli/config.toml` manually:

```toml
[accounts.personal]
email = "you@example.com"
display-name = "Your Name"
default = true

backend.type = "imap"
backend.host = "imap.example.com"
backend.port = 993
backend.encryption.type = "tls"
backend.login = "you@example.com"
backend.auth.type = "password"
backend.auth.cmd = "pass show email/imap"  # or use keyring

message.send.backend.type = "smtp"
message.send.backend.host = "smtp.example.com"
message.send.backend.port = 587
message.send.backend.encryption.type = "start-tls"
message.send.backend.login = "you@example.com"
message.send.backend.auth.type = "password"
message.send.backend.auth.cmd = "pass show email/smtp"
```

## Hermes Integration Notes

- **Reading, listing, searching, moving, deleting** all work directly through the terminal tool
- **Composing/replying/forwarding** — piped input (`cat << EOF | mail-cli template send`) is recommended for reliability. Interactive `$EDITOR` mode works with `pty=true` + background + process tool, but requires knowing the editor and its commands
- Use `--output json` for structured output that's easier to parse programmatically
- The `mail-cli account configure` wizard requires interactive input — use PTY mode: `terminal(command="mail-cli account configure", pty=true)`

## Common Operations

### List Folders

```bash
mail-cli folder list
```

### List Emails

List emails in INBOX (default):

```bash
mail-cli envelope list
```

List emails in a specific folder:

```bash
mail-cli envelope list --folder "Sent"
```

List with pagination:

```bash
mail-cli envelope list --page 1 --page-size 20
```

### Search Emails

```bash
mail-cli envelope list from john@example.com subject meeting
```

### Read an Email

Read email by ID (shows plain text):

```bash
mail-cli message read 42
```

Export raw MIME:

```bash
mail-cli message export 42 --full
```

### Reply to an Email

To reply non-interactively from Hermes, read the original message, compose a reply, and pipe it:

```bash
# Get the reply template, edit it, and send
mail-cli template reply 42 | sed 's/^$/\nYour reply text here\n/' | mail-cli template send
```

Or build the reply manually:

```bash
cat << 'EOF' | mail-cli template send
From: you@example.com
To: sender@example.com
Subject: Re: Original Subject
In-Reply-To: <original-message-id>

Your reply here.
EOF
```

Reply-all (interactive — needs $EDITOR, use template approach above instead):

```bash
mail-cli message reply 42 --all
```

### Forward an Email

```bash
# Get forward template and pipe with modifications
mail-cli template forward 42 | sed 's/^To:.*/To: newrecipient@example.com/' | mail-cli template send
```

### Write a New Email

**Non-interactive (use this from Hermes)** — pipe the message via stdin:

```bash
cat << 'EOF' | mail-cli template send
From: you@example.com
To: recipient@example.com
Subject: Test Message

Hello from Mail CLI!
EOF
```

Or with headers flag:

```bash
mail-cli message write -H "To:recipient@example.com" -H "Subject:Test" "Message body here"
```

Note: `mail-cli message write` without piped input opens `$EDITOR`. This works with `pty=true` + background mode, but piping is simpler and more reliable.

### Move/Copy Emails

Move to folder:

```bash
mail-cli message move 42 "Archive"
```

Copy to folder:

```bash
mail-cli message copy 42 "Important"
```

### Delete an Email

```bash
mail-cli message delete 42
```

### Manage Flags

Add flag:

```bash
mail-cli flag add 42 --flag seen
```

Remove flag:

```bash
mail-cli flag remove 42 --flag seen
```

## Multiple Accounts

List accounts:

```bash
mail-cli account list
```

Use a specific account:

```bash
mail-cli --account work envelope list
```

## Attachments

Save attachments from a message:

```bash
mail-cli attachment download 42
```

Save to specific directory:

```bash
mail-cli attachment download 42 --dir ~/Downloads
```

## Output Formats

Most commands support `--output` for structured output:

```bash
mail-cli envelope list --output json
mail-cli envelope list --output plain
```

## Debugging

Enable debug logging:

```bash
RUST_LOG=debug mail-cli envelope list
```

Full trace with backtrace:

```bash
RUST_LOG=trace RUST_BACKTRACE=1 mail-cli envelope list
```

## Tips

- Use `mail-cli --help` or `mail-cli <command> --help` for detailed usage.
- Message IDs are relative to the current folder; re-list after folder changes.
- For composing rich emails with attachments, use MML syntax (see `references/message-composition.md`).
- Store passwords securely using `pass`, system keyring, or a command that outputs the password.

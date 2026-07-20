# Changelog

## Unreleased

### Added

- Typed community skill registry lookup and skill installation APIs.
- Typed MCP server, tool, and server-configuration discovery APIs.
- Runtime and startup plan-mode support through `autohand.planModeSet`.
- A committed 5-warmup/50-sample startup performance gate.

### Fixed

- Detect the standard `autohand` executable on `PATH` before legacy platform binaries.
- Preserve notifications for independent prompt and global event consumers.
- Treat the prompt RPC's `{success: true}` response as acceptance and continue
  streaming until the CLI emits the terminal `agent_end` event.
- Abort and drain an accepted turn when a caller closes its prompt stream early;
  retire the subprocess if the terminal event does not arrive within two seconds.
- Roll back the CLI subprocess when post-start configuration fails.
- Keep all documented top-level exports compatible while loading them lazily.
- Reject live `skills` reassignment or rebuild so a running CLI client cannot be replaced or leaked.
- Bound prompt, subscriber, and compatibility event queues while transferring a
  pre-subscription backlog exactly once to the first global event consumer.
- Serialize process lifecycle and stdin writes, coalesce concurrent starts, and
  remove pending response callbacks when a request is cancelled during a write.
- Reap a still-live child after stdout closes, including TERM-ignoring children,
  without allowing delayed cleanup to affect a replacement process generation.
- Close blocked event subscribers and reset both client and SDK state on CLI
  termination so the same SDK instance can be started again safely.
- Reject startup if stdout closes after the final plan-mode or feature-settings
  response, rather than committing a stale started state.
- Avoid lifecycle-lock re-entry when a process exits during startup and preserve
  an unterminated final JSON response before handling EOF.

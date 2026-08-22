# Terminal read

A **terminal read** is a read-only capture of a live crew's terminal pane. A pane is one visible terminal
area managed by `tmux`, a program that keeps terminal sessions running and arranges them into panes.

## Why terminal read exists

Sometimes an operator needs to see what a live crew is doing now. A summary can hide the exact error or
prompt on screen. The terminal read shows the current pane without giving the browser control of it.

Terminal text is not ctower authority. It can be incomplete, wrapped by the terminal width, or gone when a
session ends. It does not prove that a stage passed or that a ticket is complete.

## Current status

The former browser terminal-read routes are retired. The separately activated CT-I1-021 console viewer
server foundation is read-only and does not itself provide a product browser route, typing, or terminal
control. Missing, stale, redacted, or unavailable live output must remain explicit; terminal text is never
proof of a passed stage or completed ticket.

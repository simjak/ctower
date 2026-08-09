# Terminal read

A **terminal read** is a read-only capture of a live crew's terminal pane. A pane is one visible terminal
area managed by `tmux`.

## Why terminal read exists

Sometimes an operator needs to see what a live crew is doing now. A summary can hide the exact error or
prompt on screen. The terminal read shows the current pane without giving the browser control of it.

Terminal text is not ctower authority. It can be incomplete, wrapped by the terminal width, or gone when a
session ends. It does not prove that a stage passed or that a ticket is complete.

## How to use it

Open `/team/<seat>` to see one terminal tab for each live crew in that seat. Open
`/crew/<crew-name>` to see one crew and its terminal.

The page shows when the pane was captured. It also states whether text was redacted before display.
**Redacted** means that secret-like text was removed from the rendered copy. If the crew is not running,
the page says that no live pane was found. If the source cannot be reached, the page reports that failure.

The view polls for a new capture. It cannot type, steer, stop, or restart work. Use the recorded ticket and
session facts when you need history. Use the terminal only for live observation.

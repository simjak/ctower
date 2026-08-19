# Platform health sweep

Run the configured platform health probe and report its verdict, never a status-page claim. A
healthy sweep is one line naming the observed environments, reachable pod ratio, and endpoint
result. An unhealthy sweep is classified before it is escalated: known-benign classes are named
and dismissed with their evidence, and anything left over is an incident that names the failing
section and the seat it is escalated to. Never close the window silently on an unhealthy read;
attach the probe output as the Inbox work-item artifact.

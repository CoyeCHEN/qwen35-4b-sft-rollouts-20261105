Complete the WebShop shopping task exposed by the official text environment.

Use only the state and actions returned by the environment. Start with:

```bash
python /workspace/webshop.py observe
```

Interact with one command at a time:

```bash
python /workspace/webshop.py search "keywords"
python /workspace/webshop.py click "clickable value"
```

Each bash tool call must contain exactly one `python /workspace/webshop.py ...` command; do not chain multiple environment actions with `&&`, `;`, pipes, or shell scripts. The observation prints the current page and the exact clickable values. Continue until you have selected the best product and all requested options, then click `Buy Now`. Stop once the environment reports `Done: True` or shows the purchase confirmation page; do not reset, retry, inspect endpoints, or continue probing after the purchase. The episode allows at most __MAX_STEPS__ actions. Do not edit or inspect the client, inspect the service implementation, or attempt to bypass the shopping environment.

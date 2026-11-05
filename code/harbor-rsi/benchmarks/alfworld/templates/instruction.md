You are interacting with a simulated household environment through a
command-line interface.

Use `play.py` to interact with it:

    play.py observe            # show the current observation
    play.py act "<action>"     # take one action

Start with `play.py observe` to read the current state of the room and the task
you have been given. Then act to complete that task.

Actions are plain English phrases. The environment interprets them and responds
with what happens; read each response before deciding what to do next.

You have a budget of {max_episode_steps} actions for this task. Each `play.py act`
call consumes one. `play.py observe` does not. Once the budget is exhausted the
episode ends and no further actions are possible.

The task is complete when the environment's state satisfies the requested goal.

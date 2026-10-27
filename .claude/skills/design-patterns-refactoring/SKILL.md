---
name: design-patterns-refactoring
description: >-
  Reference for the 22 Gang-of-Four design patterns and the 21 refactoring.guru
  code smells, with use cases and trade-offs written for a Python
  machine-learning pipeline. Use this skill when you start a new repository or
  module and choose its structure, when you plan a new feature that has more
  than one valid design, or when you refactor existing code and need to name
  what is wrong before you fix it. Also use it when you review a pull request
  for structural issues, when a function or a class is hard to change without
  breaking something else, or when you decide whether a design pattern is
  actually needed instead of over-engineering. Trigger phrases: "what pattern
  should I use", "how should I structure this", "this class does too much",
  "refactor this", "design this feature", "code smell", "am I over-engineering
  this".
---

# Design Patterns and Code Smells

This skill helps at two moments: when you pick a structure while you plan new code, and when you name what is wrong with existing code before you refactor it. The content comes from refactoring.guru, based on the design patterns from the Gang of Four (the four original authors of the pattern catalog) and the code smell catalog from Martin Fowler. This version reframes that content for a codebase that runs a Python machine-learning pipeline.

## How to use this skill

### When you plan a new module or feature

1. Find what actually varies or is uncertain in your design: the type of object you create, the algorithm you use, the structure of the data (a tree or a chain), the state an object moves through, or whether you must adapt an external interface.
2. Check the matching row in the decision guide below. Then read that pattern's full entry in `references/design-patterns.md`, and make sure that your situation matches its "Problem it solves" list, not only its name.
3. If nothing in your situation matches a "Problem it solves" item, do not use a pattern. A plain function, a dictionary of callables, or a dataclass is often correct in Python. Reaching for a pattern with no concrete driver is the Speculative Generality smell (see `references/code-smells.md`).

### When you refactor existing code

1. Name the smell first, using `references/code-smells.md`. For example, say that a function is a Long Method or that code shows Feature Envy. Do not just say that the code needs cleanup.
2. Use that smell's Treatment and refactoring techniques list to pick one specific technique, such as Extract Method or Introduce Parameter Object, instead of an unfocused rewrite.
3. Only use a full design pattern when the smell's entry names one as the fix, such as Switch Statements pointing to Strategy or State. Most smells need only a plain technique, with no pattern.

### During code review

When a diff adds a large function or class, a long parameter list, a new `if` and `elif` chain on a type field, or a deep call chain, name the smell in your review comment. Point to the specific technique. Do not just say that the code is messy.

## Guardrails: patterns are easy to overuse

- Use a pattern only when you can point to a specific item in the "Problem it solves" list in `references/design-patterns.md` that matches a problem you have now. Do not use a pattern for a possible future need. Flexibility added ahead of need is the Speculative Generality smell, not good design.
- Try the simplest fix before you use a class-based pattern. Python gives you first-class functions, duck typing, and dataclasses. Many patterns from the Gang of Four collapse into a few lines in Python. For example, Strategy can be just a function parameter or a dictionary of callables, and Template Method can be just a loop that calls a function you pass in.
- Many style guides limit function length and forbid function definitions nested inside other functions, for this same reason. Reaching that limit is a Long Method or Large Class smell. Go to `references/code-smells.md` for the specific Extract Method or Extract Class technique, instead of splitting the code at an arbitrary line count.
- In most machine-learning codebases, production code belongs in versioned modules or packages, and notebooks stay for exploration only. If you plan to fix Duplicate Code across copies of a notebook, extract the shared logic into one tested module function. Do not just delete the duplicate notebook.

## Quick decision guide

| Symptom or need | Look at |
|---|---|
| A constructor or function with many optional parameters, or a "telescoping constructor" | Long Parameter List smell → Builder pattern |
| A repeated `if`, `elif`, or `match` chain that branches on a type or category field, and this repeats in more than one place | Switch Statements smell → Strategy, State, or polymorphism |
| You need one shared instance across the whole application, such as a client, a cache, or a configuration object | Singleton pattern, but read the testability caution in its entry first |
| An object changes its behavior depending on its mode or state, with transitions between modes | State pattern |
| You need to swap an algorithm or a model-fitting approach at run time or through configuration | Strategy pattern (in Python, often just a function parameter) |
| Several near-identical classes or functions differ only in a few steps | Template Method pattern, or fix it as the Duplicate Code smell |
| A third-party library's interface does not match what your code expects | Adapter pattern |
| A big library or subsystem, such as a Bayesian modeling library, needs many setup steps just to get one result | Facade pattern |
| An object needs new behavior added while the program runs, and you want to combine behaviors freely | Decorator pattern |
| You are building a complex object or tree of nested pipeline steps | Composite pattern, with Builder for construction |
| Millions of similar small objects are straining memory | Flyweight pattern |
| You need lazy initialization, caching, access control, or logging in front of an expensive or real object | Proxy pattern |
| You need to notify several unrelated consumers when something happens, such as a model finishing training or a run completing | Observer pattern |
| A group of components has grown tangled direct references to each other | Mediator pattern, or fix it as Divergent Change or Shotgun Surgery |
| You need to undo or roll back an in-place change | Memento pattern, paired with Command |
| You need to add an operation, such as export or cost estimate, across a mixed tree without changing its classes | Visitor pattern |
| A method reaches into another object's data more than its own | Feature Envy smell → Move Method |
| You see a long chain, such as `a.b().c().d()` | Message Chains smell → Hide Delegate |
| A class only forwards calls to another class, with no added logic | Middle Man smell → Remove Middle Man, unless it is an intentional Proxy or Decorator |
| Unused parameters or classes exist "just in case" for a future need that has not happened | Speculative Generality smell → delete them |

## References

- `references/design-patterns.md`: all 22 patterns from the Gang of Four, grouped as Creational, Structural, and Behavioral. Each entry gives the intent, concrete trigger conditions, trade-offs, relations to other patterns, and a Python example.
- `references/code-smells.md`: all 21 code smells, grouped as Bloaters, Object-Orientation Abusers, Change Preventers, Dispensables, and Couplers. Each entry gives the symptoms, causes, named refactoring techniques, related patterns, and a Python example.

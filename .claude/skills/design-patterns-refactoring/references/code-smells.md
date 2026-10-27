# Code Smell Catalog

Source: [refactoring.guru/refactoring/smells](https://refactoring.guru/refactoring/smells) — the 21-smell catalog organized into 5 categories (Bloaters, Object-Orientation Abusers, Change Preventers, Dispensables, Couplers). Every entry lists: **Signs and symptoms**, **Reasons for the problem**, **Treatment / refactoring techniques**, **Related design pattern(s)**, and a **Python/ML example** grounded in this repo's kind of code.

Naming the smell before refactoring matters: it tells you which specific technique to reach for instead of an unfocused rewrite.

---

## Bloaters

Things that have grown so large (a method, class, or parameter list) that they're hard to work with. They usually accumulate gradually rather than being written that way.

### Long Method
- **Signs and symptoms**: A method has too many lines (rule of thumb: any method longer than ~10 lines should make you start asking questions); it does many unrelated things and is hard to read top to bottom or name concisely.
- **Reasons for the problem**: Methods grow incrementally as features are added — extending an existing method is easier in the moment than creating a new one, so complexity accumulates into "spaghetti code."
- **Treatment / refactoring techniques**: Extract Method, Replace Temp with Query, Introduce Parameter Object, Preserve Whole Object, Replace Method with Method Object, Decompose Conditional.
- **Related design pattern(s)**: None specific.
- **Python/ML example**: A `run_pipeline()` function that loads raw data, cleans it, builds features, fits the model, computes results, and writes a report — all in 300 lines with no sub-functions.

### Large Class
- **Signs and symptoms**: A class has an excessive number of fields, methods, or lines; it accumulates unrelated responsibilities over the project's life.
- **Reasons for the problem**: Classes start small and grow gradually — it's easier to bolt features onto an existing class than to design a new one (the class-level version of Long Method).
- **Treatment / refactoring techniques**: Extract Class, Extract Subclass, Extract Interface, Duplicate Observed Data.
- **Related design pattern(s)**: None specific.
- **Python/ML example**: A single `AttributionModel` class handling data loading, feature engineering, model fitting, MCMC diagnostics, plotting, and dashboard export, instead of separate collaborators per concern.

### Primitive Obsession
- **Signs and symptoms**: Using primitives (ints, strings, floats) instead of small objects for concepts like currency, date ranges, or IDs; encoding meaning via magic constants; using string constants as keys into loosely-typed dicts/arrays.
- **Reasons for the problem**: Creating a primitive field is less effort than defining a proper class, so primitives accumulate.
- **Treatment / refactoring techniques**: Replace Data Value with Object, Introduce Parameter Object, Preserve Whole Object, Replace Type Code with Class, Replace Type Code with Subclasses, Replace Type Code with State/Strategy, Replace Array with Object.
- **Related design pattern(s)**: State / Strategy (via "Replace Type Code with State/Strategy").
- **Python/ML example**: A `touchpoint_type` field stored as a raw string (`"email"`, `"paid_search"`, `"display"`) compared everywhere with `if touchpoint_type == "email":` instead of a `TouchpointType` enum/class with behavior.

### Long Parameter List
- **Signs and symptoms**: More than three or four parameters in a signature; call sites become hard to read and error-prone (easy to swap argument order).
- **Reasons for the problem**: Multiple algorithms get merged into one method, requiring extra "mode" parameters; or object creation was pushed to callers to reduce class coupling, and now those objects must be passed individually.
- **Treatment / refactoring techniques**: Replace Parameter with Method Call, Preserve Whole Object, Introduce Parameter Object.
- **Related design pattern(s)**: Builder (natural fix when the parameters describe a complex object being assembled).
- **Python/ML example**: `fit_model(spend_df, conversions_df, media_channels, adstock_rate, saturation_param, seed, start_date, end_date, prior_config, chains, draws)` — a model-fitting function with 11 positional args instead of a `ModelConfig`/`FitRequest` object.

### Data Clumps
- **Signs and symptoms**: The same group of variables (e.g., `start_date`, `end_date`, `channel`) reappears together as parameters or fields across many places. Test: remove one value — if the others become meaningless, they're a clump.
- **Reasons for the problem**: Poor structural design or copy-paste programming that never got consolidated into a class.
- **Treatment / refactoring techniques**: Extract Class, Introduce Parameter Object, Preserve Whole Object.
- **Related design pattern(s)**: None specific (Introduce Parameter Object is the practical fix).
- **Python/ML example**: `channel_id`, `campaign_id`, `spend_date` passed together as three separate arguments to `compute_spend()`, `compute_impressions()`, and `compute_roas()` instead of a single `SpendKey` dataclass.

---

## Object-Orientation Abusers

Cases where OO principles are applied incompletely or incorrectly.

### Alternative Classes with Different Interfaces
- **Signs and symptoms**: Two classes perform the same job but expose differently-named methods, so they can't be used interchangeably despite being functionally equivalent.
- **Reasons for the problem**: The author of the second class was unaware an equivalent class already existed.
- **Treatment / refactoring techniques**: Rename Method, Move Method, Add Parameter, Parameterize Method, Extract Superclass.
- **Related design pattern(s)**: None specific (Extract Superclass points toward a common interface, conceptually related to Strategy).
- **Python/ML example**: A `BayesianModelAdapter.fit_model()` and a separately-written `LegacyMMMWrapper.train()` both fit a media-mix model but have incompatible method names, preventing them from being swapped in a pipeline expecting a common interface.

### Refused Bequest
- **Signs and symptoms**: A subclass only uses some inherited methods/fields; unused ones may be unimplemented or raise when called.
- **Reasons for the problem**: Inheritance was created purely to reuse superclass code, without a real "is-a" relationship.
- **Treatment / refactoring techniques**: Replace Inheritance with Delegation, Extract Superclass.
- **Related design pattern(s)**: None specific (composition-over-inheritance is the underlying principle).
- **Python/ML example**: A `CountModelPipeline` subclasses `BaseAttributionPipeline` just to reuse `load_data()` but overrides/no-ops most other inherited methods (`fit_bayesian_model`, `plot_posterior`) because its lifecycle doesn't fit the base class's assumptions.

### Switch Statements
- **Signs and symptoms**: A complex `switch`/`if-elif` chain, especially one repeated in multiple places checking the same type code.
- **Reasons for the problem**: OO designs should rarely need to branch on type; when this logic is duplicated, adding a new case means hunting down every occurrence. Key insight: "when you see switch you should think of polymorphism."
- **Treatment / refactoring techniques**: Extract Method, Move Method, Replace Type Code with Subclasses, Replace Type Code with State/Strategy, Replace Conditional with Polymorphism, Replace Parameter with Explicit Methods, Introduce Null Object.
- **Related design pattern(s)**: Strategy / State (via polymorphism-based replacements). Factory Method and Abstract Factory are explicitly legitimate uses of switch (for object creation) — don't over-apply this smell to construction code.
- **Python/ML example**: A long `if channel_type == "email": ... elif channel_type == "display": ...` block repeated in both the adstock-transform function and the attribution-report function, instead of per-channel classes implementing a common `transform()` method.

### Temporary Field
- **Signs and symptoms**: An object field is only populated under certain conditions and empty/`None` otherwise, making the class confusing to reason about.
- **Reasons for the problem**: Fields are added to hold intermediate values needed only during a specific algorithm, instead of being passed as parameters, to avoid a long parameter list.
- **Treatment / refactoring techniques**: Extract Class (Replace Method with Method Object), Introduce Null Object.
- **Related design pattern(s)**: None specific.
- **Python/ML example**: An `AttributionRunner` class with a `self._posterior_samples` attribute set only during `run_ablation_test()` and `None`/stale otherwise, causing bugs when other methods assume it's populated.

---

## Change Preventers

Smells that make modifying existing code harder and riskier than it should be.

### Divergent Change
- **Signs and symptoms**: One kind of change to a class forces edits to many unrelated methods within that same class.
- **Reasons for the problem**: Poor program structure or copy-paste programming bundled unrelated responsibilities into one class.
- **Treatment / refactoring techniques**: Extract Class, Extract Superclass, Extract Subclass.
- **Related design pattern(s)**: None specific; opposite smell is Shotgun Surgery.
- **Python/ML example**: Adding a new media channel requires editing the data-loading method, the feature-engineering method, and the plotting method — all inside a single monolithic `DataManager` class — because responsibilities weren't separated.

### Parallel Inheritance Hierarchies
- **Signs and symptoms**: Every subclass of one class forces you to create a matching subclass of another class.
- **Reasons for the problem**: The paired hierarchies start manageable but become harder to extend as more subclass pairs accumulate.
- **Treatment / refactoring techniques**: Move Method, Move Field.
- **Related design pattern(s)**: None specific.
- **Python/ML example**: Adding a new `EmailTouchpoint` subclass always requires also adding a matching `EmailTouchpointSerializer` subclass elsewhere.

### Shotgun Surgery
- **Signs and symptoms**: A single logical change requires many small edits scattered across many different classes/files.
- **Reasons for the problem**: One responsibility got fragmented across numerous classes, often from over-applying Divergent Change fixes.
- **Treatment / refactoring techniques**: Move Method, Move Field, Inline Class.
- **Related design pattern(s)**: None specific; sibling smell to Divergent Change and Parallel Inheritance Hierarchies.
- **Python/ML example**: Changing how "conversion window" is defined requires edits in `data_manager.py`, `feature_builder.py`, `model_pipeline.py`, and `dashboard.py` because the concept's logic is duplicated/scattered rather than centralized.

---

## Dispensables

Things that add no value and should be simplified away or removed outright.

### Comments
- **Signs and symptoms**: A method is full of explanatory comments needed to make otherwise-unclear code make sense.
- **Reasons for the problem**: Comments often compensate for poor naming or structure — "the best comment is a good name for a method or class."
- **Treatment / refactoring techniques**: Extract Variable, Extract Method, Rename Method, Introduce Assertion.
- **Related design pattern(s)**: None specific.
- **Python/ML example**: A block in a survival-analysis module with `# this computes the hazard rate adjusted for censoring, see notebook X` above ten dense lines, instead of extracting a well-named `compute_censoring_adjusted_hazard_rate()` function.

### Duplicate Code
- **Signs and symptoms**: Two code fragments look nearly identical — literally copy-pasted, or logically equivalent despite superficial differences.
- **Reasons for the problem**: Parallel work recreating similar logic independently; time pressure favoring copy-paste over refactoring; no motivation to consolidate.
- **Treatment / refactoring techniques**: Same class → Extract Method. Subclasses → Extract Method + Pull Up Field, Pull Up Constructor Body, Form Template Method, Substitute Algorithm. Unrelated classes → Extract Superclass, Extract Class. Conditionals → Consolidate Conditional Expression, Extract Method, Consolidate Duplicate Conditional Fragments.
- **Related design pattern(s)**: Template Method (via "Form Template Method").
- **Python/ML example**: `simulation_v2.ipynb` and `simulation_weekly_daily-Copy1.ipynb` contain near-identical feature-engineering cells copy-pasted with tiny tweaks, instead of a single shared function.

### Data Class
- **Signs and symptoms**: A class contains only fields plus getters/setters, with no real behavior of its own.
- **Reasons for the problem**: New classes naturally start this way, but the OOP payoff (attaching behavior to data) never gets added.
- **Treatment / refactoring techniques**: Encapsulate Field, Encapsulate Collection, Move Method, Extract Method, Remove Setting Method, Hide Method.
- **Related design pattern(s)**: None specific.
- **Python/ML example**: A `TouchpointRecord` class with only `user_id`, `timestamp`, `channel`, `spend` fields, while all logic operating on it (windowing, deduplication, attribution weighting) lives in free functions elsewhere.

### Dead Code
- **Signs and symptoms**: A variable, parameter, field, method, or class is no longer used anywhere.
- **Reasons for the problem**: Requirements changed and old code wasn't cleaned up; or complex conditionals leave unreachable branches.
- **Treatment / refactoring techniques**: Delete unused code/files, Inline Class, Collapse Hierarchy, Remove Parameter.
- **Related design pattern(s)**: None specific.
- **Python/ML example**: An old `compute_last_touch_attribution()` function left in a module from before a newer attribution method replaced it, never called anymore but still present with its imports.

### Lazy Class
- **Signs and symptoms**: A class does too little to justify the cost of understanding and maintaining it.
- **Reasons for the problem**: Either a once-useful class was refactored down to near-nothing, or it was created speculatively for functionality that never arrived.
- **Treatment / refactoring techniques**: Inline Class (near-useless classes), Collapse Hierarchy (subclasses with minimal functionality).
- **Related design pattern(s)**: None specific.
- **Python/ML example**: A `SpendAdjuster` class that only wraps a single `adjust(x) -> x * 1.0` no-op left over after a pricing-adjustment feature was descoped.

### Speculative Generality
- **Signs and symptoms**: Unused classes, methods, fields, or parameters exist "just in case" for hypothetical future needs.
- **Reasons for the problem**: Anticipatory over-engineering for features that never get built, adding complexity without payoff.
- **Treatment / refactoring techniques**: Collapse Hierarchy, Inline Class, Inline Method, Remove Parameter, deleting unused fields.
- **Related design pattern(s)**: None specific — this is the smell to watch for whenever you're tempted to introduce a design pattern "for future flexibility" without a concrete current need.
- **Python/ML example**: A `model_backend: str = "vendor_a"` parameter threaded through the whole pipeline "in case we swap MMM libraries later," with every other branch unimplemented and untested.

---

## Couplers

Excessive coupling between classes, or replacing coupling with unnecessary indirection.

### Feature Envy
- **Signs and symptoms**: A method uses another object's data far more than its own — it's "more interested" in a foreign class than its own.
- **Reasons for the problem**: Commonly appears after fields were moved into a data class but the operations using that data weren't moved along with it.
- **Treatment / refactoring techniques**: Move Method (relocate the whole method), Extract Method (split out the externally-focused part, then move it).
- **Related design pattern(s)**: Strategy and Visitor are intentional exceptions — they deliberately separate behavior from the data-holding class to allow dynamic behavior swapping.
- **Python/ML example**: A `ReportBuilder.summarize()` method that reaches into `spend_data.raw_df`, `spend_data.channel_map`, and `spend_data.date_range` directly rather than that logic living on `SpendData` itself.

### Inappropriate Intimacy
- **Signs and symptoms**: One class reaches into another's internal fields/methods, making the two tightly and mutually dependent.
- **Reasons for the problem**: Classes evolved "too close together," violating encapsulation.
- **Treatment / refactoring techniques**: Move Method, Move Field, Extract Class, Hide Delegate, Change Bidirectional Association to Unidirectional, Replace Delegation with Inheritance.
- **Related design pattern(s)**: None specific.
- **Python/ML example**: `CountModel` directly mutates `DataManager._internal_cache` rather than going through a public API, so a change to `DataManager`'s internals silently breaks `CountModel`.

### Incomplete Library Class
- **Signs and symptoms**: A third-party library is missing functionality you need, and you can't modify it because it's external.
- **Reasons for the problem**: The library author didn't anticipate or chose not to implement the needed feature.
- **Treatment / refactoring techniques**: Introduce Foreign Method, Introduce Local Extension.
- **Related design pattern(s)**: Local Extension is effectively an Adapter/Decorator-style wrapper, though refactoring.guru doesn't name it as such.
- **Python/ML example**: A third-party Bayesian modeling library, installed from its git source rather than a pinned release, lacks a convenience method to export posterior draws in the wide format a dashboard needs, so a small extension module wraps the library's `Model` class with an added `to_dashboard_frame()` helper instead of forking the library.

### Message Chains
- **Signs and symptoms**: Long call chains like `a.b().c().d()`, walking through several intermediate objects to reach the one actually needed.
- **Reasons for the problem**: The client becomes coupled to the full navigation path through the object structure; if that structure changes, every chain using it breaks.
- **Treatment / refactoring techniques**: Hide Delegate, Extract Method, Move Method.
- **Related design pattern(s)**: None as a fix, but hiding delegates too aggressively risks introducing Middle Man.
- **Python/ML example**: `pipeline.model.trace.posterior.get("beta_media").values.mean()` chained directly in report code, rather than exposing a `pipeline.get_media_coefficient_means()` method.

### Middle Man
- **Signs and symptoms**: A class exists solely to delegate calls to another class, adding no behavior of its own.
- **Reasons for the problem**: Either the overcorrected result of eliminating Message Chains, or functionality was gradually moved out of it over time, leaving an "empty shell."
- **Treatment / refactoring techniques**: Remove Middle Man.
- **Related design pattern(s)**: Proxy and Decorator are legitimate, intentional "middle man" structures — do not remove those. A middle man is also sometimes deliberately kept to reduce interclass dependencies.
- **Python/ML example**: A `PipelineFacade.fit()` method that does nothing but call `self._inner_pipeline.fit()` with the same arguments and no added logic, existing only because the inner pipeline used to be private.

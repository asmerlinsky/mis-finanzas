# Design Pattern Catalog

Source: [refactoring.guru/design-patterns](https://refactoring.guru/design-patterns) (the 22-pattern Gang-of-Four catalog; refactoring.guru omits Interpreter as rarely used in practice). All examples below are framed for a Python data/ML-pipeline codebase like this one, not the generic GUI/game examples on the source site.

Every entry lists: **Intent**, **Problem it solves / when to reach for it** (concrete trigger conditions — treat these as a checklist, not vibes), **When NOT to use it / trade-offs**, **Relations to other patterns**, and a **Python/ML example**.

---

## Creational Patterns

Creational patterns deal with object creation — hiding *how* an object gets built so calling code depends on *what* it needs, not the concrete construction steps.

### Factory Method
- **Intent**: Lets a class hand off the actual instantiation of an object to subclasses (or an overridable method), so the calling code depends only on a common product interface rather than on concrete classes.
- **Problem it solves / when to reach for it**:
  - You don't know beforehand the exact types/dependencies of the objects your code needs to work with, and expect to add more later.
  - You want to let users of your library/framework extend its internal components via subclassing rather than modifying the framework itself.
  - You want to save resources by reusing/caching existing objects instead of always constructing new ones.
  - Your creation code is scattered across the app in conditionals that branch on object type — a sign construction logic should be centralized.
- **When NOT to use it / trade-offs**: Introduces a new class hierarchy of creators — best applied when a creator hierarchy already exists (less overhead) rather than introduced wholesale into simple code.
- **Relations to other patterns**: Often the starting point designs evolve from toward Abstract Factory, Prototype, or Builder as requirements grow. Abstract Factory is often implemented using several Factory Methods. Is a specialization of / step within Template Method. Vs. Prototype: Factory Method needs a subclass per product; Prototype avoids that but requires the object to support proper cloning.
- **Python/ML example**: A `DataLoader` base class has a `create_reader()` factory method; `CSVDataLoader`, `ParquetDataLoader`, and `BigQueryDataLoader` subclasses override it to return the right reader, so pipeline code never needs to know which concrete reader is in use.

### Abstract Factory
- **Intent**: Lets you produce whole families of related objects through a shared interface, guaranteeing objects created together are mutually compatible, without the client knowing which concrete family/variant it's using.
- **Problem it solves / when to reach for it**:
  - Your code needs to work with multiple families of related products but shouldn't depend on their concrete classes.
  - You need to guarantee objects created together are compatible (never accidentally mix pieces from two families).
  - A class's responsibilities are blurred by a pile of Factory Methods for different product types — pulling them into a dedicated factory class restores single responsibility.
- **When NOT to use it / trade-offs**: Adds many new interfaces/classes (one abstract factory + one interface per product + one concrete factory per family) — complexity you shouldn't pay for if you don't actually have multiple product families.
- **Relations to other patterns**: Same lineage as Factory Method/Builder/Prototype. Often built from a set of Factory Methods (or Prototype-based composition). Can substitute for Facade when hiding subsystem object creation. Pairs with Bridge to manage abstraction/implementation hierarchies. Concrete factories are frequently Singletons.
- **Python/ML example**: An `ExperimentFactory` interface with `SklearnExperimentFactory` and `PyTorchExperimentFactory` implementations, each producing a matched family of `Model`, `Preprocessor`, and `MetricsLogger` — guaranteeing you never combine a PyTorch model with a sklearn-only preprocessor.

### Builder
- **Intent**: Separates the step-by-step construction of a complex object from its final representation, so the same construction process can produce different configurations of the object.
- **Problem it solves / when to reach for it**:
  - You're facing the "telescoping constructor" problem — many overloaded constructors, or one constructor with a huge parameter list mostly unused per call.
  - The object needs many optional fields/parts and you want to build it incrementally.
  - You need several different representations of a product from largely the same construction steps.
  - You're constructing complex composite/tree-like structures where deferred or recursive construction helps.
- **When NOT to use it / trade-offs**: Requires new classes (builder(s), optionally a director) — overkill for objects with few parameters or simple, non-varying construction.
- **Relations to other patterns**: Same lineage as Factory Method/Abstract Factory/Prototype. Vs. Abstract Factory: Builder constructs one complex object step-by-step (and can run extra steps after creation); Abstract Factory returns families of products immediately. Works well with Composite for recursive tree structures. Can combine with Bridge (director = abstraction, builders = implementations). Can be a Singleton when only one builder instance is needed.
- **Python/ML example**: A `ModelConfigBuilder` chains `.set_architecture(...)`, `.add_regularization(...)`, `.set_optimizer(...)`, `.set_callbacks(...)` to assemble a `TrainingConfig`, avoiding a single constructor with a dozen optional positional args.

### Prototype
- **Intent**: Lets you create new objects by copying an existing "prototype" instance rather than instantiating and re-configuring a class from scratch, without coupling the copying code to concrete classes.
- **Problem it solves / when to reach for it**:
  - You need to duplicate an object known only through an interface, not its concrete class (common with objects handed to you by third-party code).
  - Some fields are private/inaccessible externally, so the object itself must know how to clone itself.
  - You want to avoid a subclass explosion that exists purely to represent pre-configured variants — instead keep a registry of prototype instances and clone the one you need.
  - Constructing from scratch is expensive; cloning an already-initialized instance is cheaper.
- **When NOT to use it / trade-offs**: Cloning objects with circular/complex nested references is tricky — deep-copy logic can be error-prone.
- **Relations to other patterns**: Same lineage as Factory Method/Abstract Factory/Builder. Abstract Factory can be built around Prototype instead of Factory Methods. Useful with Command for undo-stack snapshots. Complements Composite and Decorator for cloning nested structures. Vs. Factory Method: no parallel creator hierarchy needed, but the class must support cloning. Simpler alternative to Memento for objects without complicated external references. Can be a Singleton.
- **Python/ML example**: Keep a `baseline_pipeline_config` prototype (data paths, feature flags, hyperparameters pre-set); for each experiment call `.clone()` and tweak one or two fields instead of re-specifying the whole config or subclassing per variant.

### Singleton
- **Intent**: Ensures a class has only one instance in the running process and gives the rest of the codebase a single, well-known access point to it.
- **Problem it solves / when to reach for it**:
  - You need exactly one shared instance available to all clients — e.g., coordinating access to a shared resource such as a connection pool or config/log file.
  - You want something stricter/safer than a global variable (protected instance, still globally reachable).
  - You want to consolidate instance-creation/initialization logic in one place.
- **When NOT to use it / trade-offs**:
  - Violates Single Responsibility — the class manages both its core job and its own lifecycle.
  - Can mask poor design where unrelated components know too much about each other via the shared instance.
  - Needs care in multithreaded contexts to avoid race conditions creating multiple instances.
  - Makes unit testing harder — private constructors/static access are hard to mock.
- **Relations to other patterns**: A Facade is often turned into a Singleton. Resembles Flyweight, but differs in intent — Flyweight enables many instances sharing immutable state to save memory; Singleton restricts to exactly one, generally mutable, instance. Abstract Factories, Builders, and Prototypes are commonly Singletons themselves.
- **Python/ML example**: A `FeatureStoreClient` singleton wraps the connection/cache to the feature store so training, batch scoring, and validation all share one connection instead of each module opening its own.
- **Caution for this codebase**: Singletons resist unit testing and hide dependencies — prefer passing a shared instance explicitly (dependency injection) unless there's a hard constraint (e.g., a genuinely process-wide resource) forcing it.

---

## Structural Patterns

Structural patterns deal with how objects and classes are composed into larger structures while keeping those structures flexible and efficient.

### Adapter
- **Intent**: Lets two objects with mismatched interfaces work together by inserting a translator object in between, without touching either original object's code.
- **Problem it solves / when to reach for it**:
  - An existing class/library's interface doesn't match what your codebase expects, and you can't modify its source (e.g., third-party package).
  - Your app produces/consumes one data format but a library only understands another — you need a conversion layer, not a rewrite.
  - You want to reuse existing subclasses that lack common functionality that can't be added to their shared parent.
  - You'd rather wrap objects dynamically in an adapter than duplicate glue code across every subclass that needs it.
- **When NOT to use it / trade-offs**: Adds extra classes/interfaces — sometimes it's simpler to modify the service class directly if you actually can.
- **Relations to other patterns**: Unlike Bridge (designed upfront, before hierarchies diverge), Adapter is applied retroactively. Unlike Decorator (preserves/extends an interface), Adapter changes the interface entirely. Vs. Proxy (same interface) and Facade (wraps a whole subsystem): Adapter typically wraps one object to translate one interface into another.
- **Python/ML example**: Your internal `Model` interface expects `.predict(X)`, but a third-party modeling library exposes a completely different API (`.sample_posterior()`, custom array outputs). A thin `LibraryAdapter` implements your internal interface and internally calls the library's real methods, so the rest of the pipeline never touches the library's native API directly.

### Bridge
- **Intent**: Splits one bloated class (or tangled related classes) into two independent hierarchies — an "abstraction" and an "implementation" — connected by composition, so each can be extended on its own.
- **Problem it solves / when to reach for it**:
  - A class varies along two independent dimensions (e.g., shape × color), and subclassing for every combination causes combinatorial explosion.
  - You need to split a monolithic class with several variants tied to different platforms/backends (e.g., different database servers).
  - You need to extend a class along orthogonal dimensions independently.
  - You need to switch implementations at runtime.
- **When NOT to use it / trade-offs**: Adds complexity if applied to a hierarchy that's already cohesive — only use it when the two dimensions genuinely need to vary independently.
- **Relations to other patterns**: Related to Adapter, State, Strategy, Abstract Factory, Builder. Bridge/State/Strategy all rely on composition and look structurally similar but solve different problems. Can combine with Abstract Factory (pairing implementations with abstractions) and Builder (director = abstraction role).
- **Python/ML example**: An `AttributionModel` abstraction (touchpoint attribution, MMM attribution) that runs against multiple backend implementations — a local pandas/numpy backend for prototyping and a distributed Spark/BigQuery backend for production — evolving independently instead of a `Pandas...`/`Spark...` subclass per combination.

### Composite
- **Intent**: Lets you build tree-shaped structures of objects and treat individual leaf objects and entire branches through the same uniform interface.
- **Problem it solves / when to reach for it**:
  - Your domain model is naturally a tree/hierarchy nested to arbitrary depth.
  - You need to compute something over that structure without special-casing "leaf vs. container" at every call site.
  - You want simple and composite elements usable interchangeably through one common interface.
- **When NOT to use it / trade-offs**: Forcing a common interface onto leaf and container classes with genuinely different responsibilities can overgeneralize that interface until it's too abstract to be meaningful.
- **Relations to other patterns**: Pairs with Builder (constructing composite trees step by step), Chain of Responsibility (parent-child request passing), Iterator (traversal), Visitor (operations over the whole tree). Structurally resembles Decorator (both recursive composition) but Composite aggregates results from many children, while Decorator wraps exactly one child to add behavior.
- **Python/ML example**: A feature-engineering pipeline composed of `Step` objects and `Pipeline` objects that are themselves composed of other steps or sub-pipelines; calling `.transform(df)` works uniformly on a single step or a whole nested pipeline.

### Decorator
- **Intent**: Lets you attach new behavior to an individual object at runtime by wrapping it in one or more "wrapper" objects, instead of baking every combination of behavior into subclasses.
- **Problem it solves / when to reach for it**:
  - You need to add behaviors to objects dynamically, at runtime, without altering existing code that uses them.
  - Supporting many optional, combinable behaviors via inheritance would cause a combinatorial explosion of subclasses.
  - You want composable layers you can mix and match at runtime.
  - Extending via inheritance is awkward or impossible, so wrapping is the only realistic way to reuse existing behavior.
- **When NOT to use it / trade-offs**: Hard to remove a specific wrapper from the middle of a stack; behavior can depend on wrapper order (fragile); the assembly code for all the layers can get verbose.
- **Relations to other patterns**: Vs. Adapter (different interface) and Proxy (similar structure, but Proxy manages the object's lifecycle itself while Decorator's stack is client-controlled). Vs. Chain of Responsibility (handlers can stop propagation; decorators always pass through). Vs. Composite (one wrapped child + added behavior vs. many children + aggregation). Also related to Prototype (cloning wrapped structures) and Strategy (Strategy changes the algorithm's "guts"; Decorator changes the "skin").
- **Python/ML example**: A base `SpendResponseCurve.predict(spend)` wrapped by a `CachingDecorator` to avoid recomputing repeated spend levels, further wrapped by a `LoggingDecorator` recording every call for observability — both added without touching the curve-fitting code.

### Facade
- **Intent**: Gives client code one simple, high-level entry point in front of a complex subsystem made of many interacting classes, hiding the wiring/sequencing details.
- **Problem it solves / when to reach for it**:
  - Integrating a sophisticated library/framework requires initializing many objects and calling methods in a particular order — leaking that into business logic tightly couples it to implementation details.
  - You just need a limited, straightforward interface to a complex, growing subsystem.
  - You want to structure a large system into layers with a facade at each boundary as the single entry point.
- **When NOT to use it / trade-offs**: A facade risks becoming a "god object" coupled to nearly every class in the subsystem, turning into a maintenance bottleneck.
- **Relations to other patterns**: Vs. Adapter (wraps a whole subsystem vs. one incompatible object). Vs. Abstract Factory (alternative when the real goal is hiding object *creation*). Vs. Flyweight (many small shared objects vs. one subsystem-fronting object). Vs. Mediator (Facade simplifies an interface without adding behavior; Mediator centralizes and adds communication logic). Often a Singleton. Vs. Proxy (same interface vs. Facade's new, simplified interface).
- **Python/ML example**: Fitting/inference with a Bayesian modeling library involves constructing an input-data object, configuring priors, running MCMC, and post-processing a posterior — a `ModelFacade.fit_and_summarize(data, config)` wraps all of that so the rest of the pipeline calls one function instead of replicating the library's setup sequence everywhere.

### Flyweight
- **Intent**: Cuts memory usage when you need huge numbers of similar objects, by sharing the data identical across many instances ("intrinsic" state) in one shared object, leaving only per-instance ("extrinsic") data stored separately.
- **Problem it solves / when to reach for it**:
  - You need a very large number of essentially similar objects in memory at once.
  - Fully materializing them independently would barely fit, or wouldn't fit, in available RAM.
  - A meaningful chunk of each object's state is duplicated identically across many instances and can be factored out.
  - The memory problem can't reasonably be solved another way — this is a targeted fix for a measured constraint, not a default choice.
- **When NOT to use it / trade-offs**: Trades memory for CPU (recomputing/looking up extrinsic context), adds complexity, and can confuse the team about which state lives where.
- **Relations to other patterns**: Composite trees can use Flyweight for leaf nodes to save memory. Vs. Facade (many small shared objects vs. one object fronting a subsystem). Vs. Singleton (superficially similar, but Flyweight allows many instances differing by intrinsic state and is meant to be immutable; Singleton is exactly one, generally mutable, instance).
- **Python/ML example**: In a touchpoint pipeline processing millions of events, share one `CampaignMetadata` flyweight per campaign ID instead of duplicating campaign fields onto every event row, keeping only per-event extrinsic fields (timestamp, user id) on the row.

### Proxy
- **Intent**: Puts a stand-in object in front of a real object with the *same interface*, so it can intercept calls and add behavior (delaying creation, checking access, caching, logging, etc.) before or after forwarding to the real object.
- **Problem it solves / when to reach for it**:
  - Lazy initialization (virtual proxy): defer creating an expensive object until it's actually needed.
  - Access control (protection proxy): only let clients meeting certain criteria reach the underlying service.
  - Remote proxy: transparently handle network communication for a service that lives elsewhere.
  - Logging proxy: record a history of requests before passing them through.
  - Caching proxy: cache and reuse results for repeated identical requests.
  - Smart reference: track object usage and free it once nobody needs it.
- **When NOT to use it / trade-offs**: Adds classes and indirection; can introduce latency since calls pass through an extra layer.
- **Relations to other patterns**: Vs. Adapter (Adapter changes the interface; Proxy keeps it identical). Vs. Decorator (similar structure, but Proxy manages the real object's lifecycle itself; the client may not know it's not talking to the real thing). Vs. Facade (Proxy fronts a single object with an identical interface; Facade fronts a whole subsystem with a new one).
- **Python/ML example**: Wrap a real, expensive-to-fit Bayesian model behind a `CachedModelProxy` exposing the identical `.predict()`/`.sample_posterior()` interface, caching results for repeated scenarios during what-if analysis, and lazily fitting the real model only on first actual use.

---

## Behavioral Patterns

Behavioral patterns deal with algorithms and the assignment of responsibilities/communication between objects.

### Chain of Responsibility
- **Intent**: Builds a pipeline of handler objects where a request travels down the chain until some handler acts on it (or nobody does), so the sender doesn't need to know which handler will process it.
- **Problem it solves / when to reach for it**:
  - A sequence of checks/processing steps (auth → sanitize → rate-limit → cache) keeps growing and getting tangled in one method.
  - The exact set/order of processing steps isn't fully known ahead of time or must be assembled dynamically.
  - Several handlers must run in a specific, controllable order.
  - You want the set of handlers (and order) changeable at runtime.
- **When NOT to use it / trade-offs**: A request can silently fall through the whole chain unhandled — easy to introduce bugs of omission. Adds indirection over tracing execution flow through multiple small objects.
- **Relations to other patterns**: Overlaps with Command, Mediator, Observer (all decouple senders from receivers). Often combined with Composite (handlers as a tree). Resembles Decorator structurally, but each handler can stop propagation, while Decorators always call the next wrapper.
- **Python/ML example**: A data-validation pipeline where each handler checks one concern — schema, null/dtype checks, deduplication, outlier flagging — passing the record on only if it doesn't reject it, so checks can be inserted/reordered/removed without touching a monolithic `validate()`.

### Command
- **Intent**: Wraps a request (an action plus its parameters) into a standalone object, so the action can be passed around, queued, logged, or undone independently of what triggers it.
- **Problem it solves / when to reach for it**:
  - Many different triggers need to invoke the same operation, and you want to avoid duplicating logic or coupling the trigger code directly to business logic.
  - You want to parameterize objects with an operation to execute later rather than immediately.
  - You need to queue, schedule, log, or serialize operations.
  - You need undo/redo — commands store enough state to reverse themselves and sit on a history stack.
- **When NOT to use it / trade-offs**: Adds an extra layer (a Command object per operation) — not worth it for simple, one-off operations.
- **Relations to other patterns**: Related to Chain of Responsibility, Mediator, Observer. Pairs with Memento for undo (Command performs the operation, Memento captures/restores state). Easily confused with Strategy — Command reifies an operation for later invocation; Strategy swaps *how* an algorithm is computed within an ongoing call.
- **Python/ML example**: Wrap each pipeline step ("impute missing values," "drop outlier rows," "encode categorical column") as a `Command` object so a transformation pipeline can be replayed, logged for audit/reproducibility, or partially undone if a step produces a bad output.

### Iterator
- **Intent**: Provides a uniform way to walk through a collection's elements one at a time without exposing the collection's internal structure.
- **Problem it solves / when to reach for it**:
  - The collection has a non-trivial structure (tree, graph, nested) and you want to hide that from client code.
  - You're duplicating traversal logic across the app for the same/similar collections.
  - You want to traverse different, possibly unknown-in-advance, structures through one consistent interface.
- **When NOT to use it / trade-offs**: Overkill for apps working only with simple collections; can be less efficient than direct access for specialized collections.
- **Relations to other patterns**: Used with Factory Method (producing the right iterator), Memento (snapshotting iteration position), Visitor (traversing while applying operations), Composite (walking trees).
- **Python/ML example**: A custom iterator over a large, chunked/streaming dataset (partitioned Parquet files or a sharded feature store) yielding mini-batches lazily, so training code calls `next(batch_iterator)` without knowing whether data comes from disk, cloud storage, or cache.

### Mediator
- **Intent**: Pulls the communication logic between a group of interacting objects into a separate "mediator," so those objects talk to the mediator instead of each other directly.
- **Problem it solves / when to reach for it**:
  - A set of components has grown a tangle of direct references to each other, and changing one risks breaking others.
  - It's hard to modify a class because it's tightly coupled to many others.
  - You can't reuse a component elsewhere because it drags along dependencies on its peers.
  - You keep creating subclasses just to reuse shared cross-component behavior.
- **When NOT to use it / trade-offs**: The mediator itself can balloon into a "God Object" that knows and controls everything.
- **Relations to other patterns**: Differs from Facade (no added functionality) — Mediator actively centralizes and coordinates communication. Related to Observer; can combine, but Mediator removes direct dependencies among colleagues while Observer sets up dynamic subscription links.
- **Python/ML example**: An experiment-orchestration object coordinating a feature-store client, a model-fitting step, and a metrics-logger — each notifies the mediator ("features ready," "fit complete") instead of calling each other directly, so swapping the metrics logger doesn't touch the fitting code.

### Memento
- **Intent**: Lets an object capture and later restore a snapshot of its own internal state without exposing that state's representation externally.
- **Problem it solves / when to reach for it**:
  - You want to snapshot an object's state to restore it later (undo).
  - You need transaction-like rollback if an operation fails partway through.
  - Exposing internal fields to build snapshots externally would break encapsulation; the object should produce its own snapshot.
- **When NOT to use it / trade-offs**: Can burn memory if snapshots are created too frequently; requires the "caretaker" to manage snapshot lifecycle; in dynamic languages there's often no real guarantee the captured state can't be mutated afterward.
- **Relations to other patterns**: Paired with Command for undo/redo. Combines with Iterator (save/restore traversal position). Prototype can substitute when the object is simple enough to just deep-copy.
- **Python/ML example**: Before an in-place feature transformation or hyperparameter search step mutates a `Dataset`/`ModelConfig`, capture a `Memento` of its state so a candidate that degrades validation performance can be rolled back instead of re-derived from scratch.

### Observer
- **Intent**: Defines a subscribe/notify mechanism so one object (the subject) can broadcast state changes to any number of interested objects without knowing who or how many they are.
- **Problem it solves / when to reach for it**:
  - A change in one object's state must propagate to others, but the set of interested objects isn't fixed and may change dynamically.
  - Some objects only need to observe another temporarily or conditionally, not via a permanent hard-wired dependency.
- **When NOT to use it / trade-offs**: Subscribers are notified in effectively random order — don't rely on notification sequencing between them.
- **Relations to other patterns**: Contrasts with Mediator (removes dependencies via a hub, vs. Observer's dynamic subscribe/unsubscribe); the two can be combined (a Mediator using Observer internally).
- **Python/ML example**: When a new model version finishes training and passes validation, `ModelTrainer` (subject) notifies subscribed observers — a deployment service, a Slack-alert notifier, a metrics dashboard updater — independently, without knowing they exist.

### State
- **Intent**: Lets an object change its behavior at runtime by delegating to one of several interchangeable "state" objects, so it behaves as though its class changed depending on internal state.
- **Problem it solves / when to reach for it**:
  - An object's behavior depends heavily on its current state, and the number of states plus state-specific behavior keeps growing.
  - A class is bloated with large conditional blocks branching on a `state` field across many methods.
  - Duplicated logic exists across similar states and their transitions in a condition-based state machine.
- **When NOT to use it / trade-offs**: Overkill when a state machine has only a couple of states or rarely changes — a simple conditional is fine.
- **Relations to other patterns**: Closely related to Strategy structurally, but State's concrete state objects know about and can trigger transitions to other states, while Strategy's algorithm objects stay independent and unaware of each other. State/Bridge/Strategy share a "composition over inheritance" structure but solve different problems.
- **Python/ML example**: A model-training job whose `run()` behavior changes depending on `TrainingState` — `Idle`, `Fitting`, `Validating`, `Failed`, `Deployed` — with transitions like "validation failed → retry with adjusted hyperparameters" living inside dedicated state classes instead of one giant conditional.

### Strategy
- **Intent**: Extracts a family of interchangeable algorithms into separate classes implementing a common interface, so the context object can swap between them at runtime instead of hardcoding one approach.
- **Problem it solves / when to reach for it**:
  - A class supports several algorithm variants and keeps growing every time a new variant is added.
  - You have several near-identical classes differing mainly in one behavior/algorithm.
  - You want to isolate algorithm details from the code that orchestrates it.
  - A class contains large conditionals choosing between algorithm variants at runtime.
- **When NOT to use it / trade-offs**: Unnecessary complexity for a couple of algorithms that rarely change; clients must understand the differences between strategies well enough to pick the right one; in Python, passing a plain function/lambda often achieves the same flexibility without a class hierarchy.
- **Relations to other patterns**: Structurally similar to Bridge, State, Adapter (all rely on composition) but each solves a distinct problem. Differs from Command (deferred invocation, not algorithm-swapping) and Template Method (composition/runtime vs. inheritance/compile-time). State can be seen as Strategy extended so the "algorithm" objects can also trigger context transitions.
- **Python/ML example**: A `ModelTrainer` accepting a pluggable `fit_strategy` (`XGBoostStrategy`, `LinearRegressionStrategy`, `LightGBMStrategy`) all implementing a common `fit(X, y) -> Model`, letting you swap the fitting algorithm via config without touching cross-validation/orchestration code.

### Template Method
- **Intent**: Defines the fixed skeleton of an algorithm in a base class, deferring only specific steps to subclasses, so the overall sequence stays consistent while individual steps vary.
- **Problem it solves / when to reach for it**:
  - Several classes implement almost-identical algorithms differing only in a handful of steps, causing duplicated code.
  - You want clients to customize only certain steps of an algorithm without letting them alter its overall structure.
  - Client code has conditionals dispatching on data type/format that could be resolved via polymorphism if classes shared a common processing interface.
- **When NOT to use it / trade-offs**: Clients are constrained by the fixed skeleton; risk of violating Liskov Substitution if a subclass suppresses a default step it doesn't need; harder to maintain as steps grow.
- **Relations to other patterns**: Factory Method is often a specialized case of Template Method (creation as one customizable step). Differs from Strategy: inheritance/fixed-at-class-definition vs. composition/swappable-at-runtime.
- **Python/ML example**: An abstract `DataIngestionPipeline` defines the fixed skeleton `load() → validate() → transform() → write()`; concrete subclasses `CsvIngestionPipeline` and `S3ParquetIngestionPipeline` override only `load()`/`validate()`, keeping shared `transform()`/`write()` logic in one place.

### Visitor
- **Intent**: Lets you add new operations to a set of existing classes by defining them in a separate "visitor" object, instead of modifying those classes directly.
- **Problem it solves / when to reach for it**:
  - You need an operation across all elements of a complex, heterogeneous object structure (e.g., a tree with several distinct node types).
  - You want to keep auxiliary behaviors (like exporting/serializing) out of core domain classes to keep their responsibilities focused.
  - You're not allowed to (or don't want to) modify existing, fragile class hierarchies just to add one more behavior that applies to only a subset of it.
- **When NOT to use it / trade-offs**: Every new element type added to the hierarchy requires updating all existing visitor implementations; visitors often can't access private fields/methods of the elements they operate on.
- **Relations to other patterns**: A more powerful variant of Command. Frequently used with Composite (operations over trees) and Iterator (traversing heterogeneous collections).
- **Python/ML example**: A `Visitor` walking a heterogeneous pipeline-config tree (`FeatureStep`, `ModelStep`, `EvalStep` nodes) where one visitor emits a Graphviz diagram and another emits a cost estimate, without adding `to_diagram()`/`estimate_cost()` methods directly onto each step class.

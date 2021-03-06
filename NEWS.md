# Release History

## Version 0.1.1

Not released yet

### Features

* New ContextualOptimizer: C-CMA-ES (based on CMA-ES)

### Documentation

* Documented `context_features` of CREPSOptimizer

## Version 0.1.0

2017/12/19

### Features

* Continuous integration with Travis CI and CircleCI
* Added docker image
* New behavior search: Monte Carlo RL
* New optimizer: relative entropy policy search (REPS)
* New optimizer: ACM-ES (CMA-ES with surrogate model)

### Bugfixes

* DMPSequence works with multiple dimensions
* Minor fixes in docstrings
* Multiple minor fixes for Travis CI
* Fixed scaling issues in C-REPS

### Documentation

* Documented merge policy
* Added meta information about the project to the manifest.xml
* Updated documentation on how to build custom MARS environments

## Version 0.0.1

2017/05/19

First public release.

### Breaking Changes

In comparison to the old behavior learning framework used by the DFKI RIC and
the University of Bremen, we changed the following details:

* Python interface: changed signature int `Environment.get_feedback(np.ndarray)`
  to `np.ndarray Environment.get_feedback()`
* Python interface: `ContextualEnvironment` is now a subclass of `Environment`
* Python interface: renamed `Environment.get_maximal_feedback` to
  `Environment.get_maximum_feedback`
* Python and C++ interface: `Behavior` constructor does not take any arguments,
  instead the function `Behavior.init(int, int)` has been introduced to
  determine the number of inputs and outputs and initialize the behavior
* Python interface: Optimizer and ContextualOptimizer are independent
* Python interface: BehaviorSearch and ContextualBehaviorSearch are independent

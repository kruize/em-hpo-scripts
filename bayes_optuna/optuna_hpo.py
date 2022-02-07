"""
Copyright (c) 2020, 2021 Red Hat, IBM Corporation and others.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import optuna

import os

from experiment import perform_experiment
from logger import get_logger

from dotenv import load_dotenv

load_dotenv()

n_trials = int(os.getenv("n_trials"))
n_jobs = int(os.getenv("n_jobs"))

logger = get_logger(__name__)

trials = []


class Objective(object):
    """
    A class used to define search space and return the actual slo value.

    Parameters:
        tunables (list): A list containing the details of each tunable in a dictionary format.
    """

    def __init__(self, tunables):
        self.tunables = tunables

    def __call__(self, trial):
        global trials

        experiment_tunables = []
        config = {}

        # Define search space
        for tunable in self.tunables:
            if tunable["value_type"].lower() == "double":
                tunable_value = trial.suggest_discrete_uniform(
                    tunable["name"], tunable["lower_bound"], tunable["upper_bound"], tunable["step"]
                )
            elif tunable["value_type"].lower() == "integer":
                tunable_value = trial.suggest_int(
                    tunable["name"], tunable["lower_bound"], tunable["upper_bound"], tunable["step"]
                )
            elif tunable["value_type"].lower() == "categorical":
                tunable_value = trial.suggest_categorical(tunable["name"], tunable["choices"])

            experiment_tunables.append({"tunable_name": tunable["name"], "tunable_value": tunable_value})

        config["experiment_tunables"] = experiment_tunables

        logger.debug("Experiment tunables: " + str(experiment_tunables))

        actual_slo_value, experiment_status = perform_experiment(experiment_tunables)

        config["experiment_status"] = experiment_status

        trials.append(config)

        if experiment_status == "prune":
            raise optuna.TrialPruned()

        actual_slo_value = round(float(actual_slo_value), 2)
        return actual_slo_value


def recommend(application_name, direction, hpo_algo_impl, id, objective_function, tunables, value_type):
    """
    Perform Bayesian Optimization with Optuna using the appropriate sampler and recommend the best config.

    Parameters:
        application_name (str): The name of the application that is being optimized.
        direction (str): Direction of optimization, minimize or maximize.
        hpo_algo_impl (str): Hyperparameter optimization library to perform Bayesian Optimization.
        id (str): The id of the application that is being optimized.
        objective_function (str): The objective function that is being optimized.
        tunables (list): A list containing the details of each tunable in a dictionary format.
        value_type (string): Value type of the objective function.
    """
    # Set the logging level for the Optuna’s root logger
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    # Propagate all of Optuna log outputs to the root logger
    optuna.logging.enable_propagation()
    # Disable the default handler of the Optuna’s root logger
    optuna.logging.disable_default_handler()

    # Choose a sampler based on the value of ml_algo_impl
    if hpo_algo_impl == "optuna_tpe":
        sampler = optuna.samplers.TPESampler()
    elif hpo_algo_impl == "optuna_tpe_multivariate":
        sampler = optuna.samplers.TPESampler(multivariate=True)
    elif hpo_algo_impl == "optuna_skopt":
        sampler = optuna.integration.SkoptSampler()

    # Create a study object
    study = optuna.create_study(direction=direction, sampler=sampler)

    # Execute an optimization by using an 'Objective' instance
    study.optimize(Objective(tunables), n_trials=n_trials, n_jobs=n_jobs)

    # Get the best parameter
    logger.info("Best parameter: " + str(study.best_params))
    # Get the best value
    logger.info("Best value: " + str(study.best_value))
    # Get the best trial
    logger.info("Best trial: " + str(study.best_trial))

    logger.debug("All trials: " + str(trials))

    recommended_config = {}

    optimal_value = {"objective_function": {
        "name": objective_function,
        "value": study.best_value,
        "value_type": value_type
    }, "tunables": []}

    for tunable in tunables:
        for key, value in study.best_params.items():
            if key == tunable["name"]:
                tunable_value = value
        optimal_value["tunables"].append(
            {
                "name": tunable["name"],
                "value": tunable_value,
                "value_type": tunable["value_type"]
            }
        )

    recommended_config["id"] = id
    recommended_config["application_name"] = application_name
    recommended_config["direction"] = direction
    recommended_config["optimal_value"] = optimal_value

    logger.info("Recommended config: " + str(recommended_config))

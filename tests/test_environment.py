import simpy

import takt


def test_package_exposes_its_version():
    assert takt.__version__ == "0.1.0"


def test_simulation_clock_advances_to_the_scheduled_time():
    env = simpy.Environment()
    finished_at: list[float] = []

    def process(env: simpy.Environment):
        yield env.timeout(7.5)
        finished_at.append(env.now)

    env.process(process(env))

    env.run()

    assert finished_at == [7.5]

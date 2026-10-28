from wmata_board.ride import Ride, moved_ride


def test_a_moved_ride_changes_trains_and_lasts_until_the_new_one_arrives():
    ride = Ride(("or1", "rd2"), 1500.0, 2000.0)
    assert moved_ride(ride, ("or1", "rd3"), 1530.0, 2300.0) == Ride(("or1", "rd3"), 1530.0, 2420.0)
    assert moved_ride(ride, ("or1", "rd3"), 1530.0, 1700.0).until == 2000.0   # never shorter

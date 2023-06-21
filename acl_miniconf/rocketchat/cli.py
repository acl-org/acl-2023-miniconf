import sys
import time
import hydra
from omegaconf import DictConfig
from rocketchat_API.rocketchat import RocketChat
from acl_miniconf.data import Conference

# Fancy countdown function for sleeping threads
def sleep_session(duration):
    for remaining in range(duration, 0, -1):
        sys.stdout.write("\r")
        sys.stdout.write("{:2d} seconds remaining.".format(remaining))
        sys.stdout.flush()
        time.sleep(1)

def connect_rocket_API(*, user_id: str, auth_token: str, server: str, session):
    rocket = RocketChat(
        user_id=user_id,
        auth_token=auth_token,
        server_url=server,
        session=session,
    )
    return rocket

@hydra.main(version_base=None, config_path='configs/rocketchat', config_name='template')
def hydra_main(cfg: DictConfig):
    conference = Conference.from
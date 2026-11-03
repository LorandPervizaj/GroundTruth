"""Read-only checks; deliberately no contact/feedback/notification writes."""

import argparse
import os

from groundtruth.automation.deployment_smoke import smoke

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--release-id", required=True)
    p.add_argument("--revision", required=True)
    p.add_argument("--serving-sha", required=True)
    p.add_argument("--image", required=True)
    a = p.parse_args()
    smoke(
        a.url,
        {
            "data_release_id": a.release_id,
            "revision": a.revision,
            "serving_source_sha": a.serving_sha,
            "image": a.image,
        },
        token=os.environ.get("METRIK_DEPLOY_HEALTH_TOKEN", ""),
        identity=bool(a.revision),
    )
    print("METRIK_READ_SMOKE_OK")

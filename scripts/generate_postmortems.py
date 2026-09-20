"""
Generates a larger, varied set of synthetic incident postmortems for
RootTrace's RAG layer.

Why a generator instead of hand-written files: we want real category
diversity (so retrieval has to genuinely discriminate) at a scale (50) that
would be slow and error-prone to hand-write. Each archetype defines the
*shape* of a failure category; instantiate() fills in random specifics
(service name, date, numbers) so no two generated postmortems are identical
text, even within the same archetype.
"""

import json
import random
from pathlib import Path

random.seed(42)  # reproducible output -- same command always regenerates the same dataset

SERVICES = [
    "checkout-api", "payment-service", "recommendation-service", "auth-service",
    "inventory-service", "notification-service", "search-service", "user-profile-service",
    "order-service", "shipping-service", "cart-service", "pricing-service",
]

AUTHORS = [
    "priya.nair", "jordan.lee", "sam.okafor", "wei.zhang", "alex.torres",
    "maria.silva", "kwame.mensah", "yuki.tanaka", "fatima.hassan", "liam.oconnor",
]


def random_date():
    year = random.choice([2023, 2024])
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{year}-{month:02d}-{day:02d}"


ARCHETYPES = [
    {
        "category": "connection-pool",
        "title_tpl": "{service} outage due to DB connection pool exhaustion",
        "summary_tpl": (
            "A caching feature deployed to {service} introduced a code path that opened a new "
            "database connection on every write but never released it back to the pool. Within "
            "minutes of deployment, the connection pool was fully exhausted ({pool_size}/{pool_size} "
            "connections in use), causing requests to fail with 500 errors."
        ),
        "root_cause_tpl": (
            "The new logic acquired a DB connection but never explicitly released it back to the "
            "pool after use, since the code assumed a context manager would handle it automatically. "
            "It did not."
        ),
        "fix_tpl": (
            "Wrapped connection acquisition in a proper context manager to guarantee release even on "
            "exceptions, and added a pool utilization alert at 80% to catch this class of bug earlier."
        ),
        "tags": ["database", "connection-pool", "caching", "resource-leak"],
    },
    {
        "category": "memory-leak",
        "title_tpl": "{service} crash due to gradual memory leak",
        "summary_tpl": (
            "{service} began crashing with OutOfMemoryError roughly every {hours} hours after a "
            "deployment that added an in-memory result cache. The cache had no eviction policy, so "
            "it grew unbounded until the process ran out of heap space."
        ),
        "root_cause_tpl": (
            "A newly introduced LRU cache implementation was missing its max-size configuration, so "
            "it accepted unlimited entries instead of evicting old ones."
        ),
        "fix_tpl": (
            "Set an explicit max_size and TTL on the cache, and added a dashboard panel tracking heap "
            "usage over time to catch slow leaks before they cause a crash."
        ),
        "tags": ["memory-leak", "caching", "oom", "crash-loop"],
    },
    {
        "category": "schema-migration",
        "title_tpl": "Request failures in {service} after a database schema migration",
        "summary_tpl": (
            "A migration renamed a column that {service}'s ORM layer still referenced by its old "
            "name, causing requests to fail with a 'column not found' error immediately after the "
            "migration ran."
        ),
        "root_cause_tpl": (
            "The migration and the application code deploy were not coordinated -- the schema change "
            "went live before the corresponding code update, creating a window where old code queried "
            "a column that no longer existed."
        ),
        "fix_tpl": (
            "Adopted a two-phase migration strategy: add the new column and dual-write to both old and "
            "new columns first, deploy the code update, then drop the old column in a later migration."
        ),
        "tags": ["database-migration", "schema-change", "deployment-coordination"],
    },
    {
        "category": "rate-limiting",
        "title_tpl": "Downstream rate-limiting causing {service} failures",
        "summary_tpl": (
            "A traffic spike of roughly {multiplier}x drove {service} to exceed its rate limit with a "
            "third-party provider. Requests beyond the limit received 429 Too Many Requests responses, "
            "which were not handled gracefully and surfaced as generic failures to users."
        ),
        "root_cause_tpl": (
            "No client-side rate limiting or backoff/retry logic existed for calls to the provider, so "
            "traffic spikes translated directly into a wall of rejected requests."
        ),
        "fix_tpl": (
            "Implemented exponential backoff with jitter for 429 responses, and added a local "
            "token-bucket rate limiter tuned just under the provider's published limit."
        ),
        "tags": ["rate-limiting", "third-party-api", "traffic-spike"],
    },
    {
        "category": "dns-networking",
        "title_tpl": "Intermittent 502 errors in {service} due to DNS resolution failures",
        "summary_tpl": (
            "Users intermittently received 502 Bad Gateway errors from {service}. The pattern was "
            "sporadic and did not correlate with any deployment. Investigation traced it to the "
            "internal DNS resolver occasionally timing out under load."
        ),
        "root_cause_tpl": (
            "The DNS resolver's cache TTL was too short relative to query volume, causing frequent "
            "cache misses that overloaded the resolver during peak traffic."
        ),
        "fix_tpl": (
            "Increased the DNS cache TTL and added a local DNS caching sidecar to each service pod to "
            "absorb query volume without hitting the central resolver every time."
        ),
        "tags": ["dns", "networking", "502-error", "infrastructure"],
    },
    {
        "category": "auth-failure",
        "title_tpl": "Widespread 401 errors in {service} after token signing key rotation",
        "summary_tpl": (
            "Following a scheduled rotation of the JWT signing key, {service} began rejecting a large "
            "fraction of valid requests with 401 Unauthorized, because tokens issued just before the "
            "rotation could no longer be verified."
        ),
        "root_cause_tpl": (
            "The key rotation process removed the old signing key immediately instead of keeping it "
            "valid for verification during a grace period, invalidating still-live tokens."
        ),
        "fix_tpl": (
            "Changed the rotation process to keep the previous key valid for verification (but not "
            "issuing) for {hours} hours after rotation, giving in-flight tokens time to expire naturally."
        ),
        "tags": ["auth", "jwt", "key-rotation", "401-error"],
    },
    {
        "category": "cache-invalidation",
        "title_tpl": "Stale data served by {service} due to cache invalidation bug",
        "summary_tpl": (
            "Users reported seeing outdated data from {service} for up to {hours} hours after updates, "
            "because a recent refactor of the cache invalidation logic silently broke the "
            "invalidation trigger for one code path."
        ),
        "root_cause_tpl": (
            "A refactor renamed the event that triggers cache invalidation, but one caller was missed "
            "and continued publishing the old event name, which no longer had a subscriber."
        ),
        "fix_tpl": (
            "Fixed the missed caller, and added an integration test that asserts every code path "
            "which mutates cached data actually publishes an invalidation event."
        ),
        "tags": ["caching", "cache-invalidation", "stale-data"],
    },
    {
        "category": "disk-space",
        "title_tpl": "{service} outage due to disk space exhaustion from log accumulation",
        "summary_tpl": (
            "{service} stopped accepting writes after its disk filled up. Investigation found that a "
            "verbose debug-logging flag left enabled after a previous incident investigation had been "
            "writing uncompressed logs at a much higher rate than normal."
        ),
        "root_cause_tpl": (
            "A debug logging flag enabled during a prior investigation was never reverted, and no "
            "alert existed for disk usage trending upward over days rather than spiking suddenly."
        ),
        "fix_tpl": (
            "Reverted the logging flag, added log rotation with compression, and added a slow-trending "
            "disk usage alert in addition to the existing near-full alert."
        ),
        "tags": ["disk-space", "logging", "infrastructure"],
    },
    {
        "category": "thread-pool-exhaustion",
        "title_tpl": "{service} request timeouts due to thread pool exhaustion",
        "summary_tpl": (
            "{service} began timing out on the majority of requests after a downstream dependency "
            "became slow. Because calls to that dependency were synchronous and blocking, the "
            "service's thread pool filled with threads waiting on it, starving unrelated requests."
        ),
        "root_cause_tpl": (
            "Calls to the slow downstream dependency had no timeout configured, so a single slow "
            "dependency could exhaust the entire thread pool indefinitely."
        ),
        "fix_tpl": (
            "Added an explicit timeout and circuit breaker around the downstream call, so a slow "
            "dependency degrades gracefully instead of exhausting shared resources."
        ),
        "tags": ["thread-pool", "timeout", "circuit-breaker", "resource-exhaustion"],
    },
    {
        "category": "bad-config-deploy",
        "title_tpl": "{service} outage from a misconfigured environment variable at deploy time",
        "summary_tpl": (
            "A deployment to {service} shipped with an incorrect value for a feature-flag environment "
            "variable, unintentionally enabling a half-finished feature in production and causing "
            "widespread request failures."
        ),
        "root_cause_tpl": (
            "The deployment pipeline did not validate environment variable values against an allowed "
            "schema before rollout, so a typo'd config value reached production undetected."
        ),
        "fix_tpl": (
            "Added config validation as a required pre-deploy check, and staged the rollout so "
            "config changes reach a small percentage of traffic before going fully live."
        ),
        "tags": ["configuration", "deployment", "feature-flag"],
    },
]


def instantiate(archetype: dict, index: int) -> dict:
    service = random.choice(SERVICES)
    author = random.choice(AUTHORS)
    values = {
        "service": service,
        "pool_size": random.choice([25, 50, 100]),
        "hours": random.choice([2, 4, 6, 8, 12, 24]),
        "multiplier": random.choice([3, 4, 5, 6, 8]),
    }
    return {
        "id": f"pm_{index:03d}",
        "title": archetype["title_tpl"].format(**values),
        "date": random_date(),
        "summary": archetype["summary_tpl"].format(**values),
        "root_cause": archetype["root_cause_tpl"].format(**values),
        "fix": archetype["fix_tpl"].format(**values),
        "tags": archetype["tags"] + [service],
    }


def generate(count: int, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, count + 1):
        archetype = ARCHETYPES[(i - 1) % len(ARCHETYPES)]
        pm = instantiate(archetype, i)
        path = output_dir / f"pm_{i:03d}_{archetype['category']}.json"
        path.write_text(json.dumps(pm, indent=2))
    print(f"Generated {count} postmortems into {output_dir}")


if __name__ == "__main__":
    generate(50, Path("mock_data/postmortems"))
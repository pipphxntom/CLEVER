"""Reset a route's cheap-tier stats. Does not claim a phase it does not have."""
import asyncio
import sys

import asyncpg

from gateway.layers.myelination import decision_from_stats, phase_of
from gateway.config import settings


async def trigger(route_class: str = "email_draft:standard"):
    pool = await asyncpg.create_pool(settings.POSTGRES_DSN)
    alpha, beta, n_obs = 50, 5, 55
    d = decision_from_stats(alpha, beta, n_obs, tau=0.92)
    print(f"Seeding {route_class}: n_obs={n_obs} phase={phase_of(n_obs, d.cheap_trials)} "
          f"p_hat={d.p_hat} lcb={d.lcb} credible={d.credible} decision={d.decision}")
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO myelination_registry
                (route_class, alpha, beta, n_obs, updated_at)
            VALUES ($1, $2, $3, $4, now())
            ON CONFLICT (route_class) DO UPDATE
            SET alpha=$2, beta=$3, n_obs=$4, updated_at=now()
            """,
            route_class, alpha, beta, n_obs,
        )
        input("Press ENTER to reset this route to cold (n_obs=0)...")
        await conn.execute(
            """
            UPDATE myelination_registry
            SET alpha=1, beta=1, n_obs=0, last_correction=now()
            WHERE route_class=$1
            """,
            route_class,
        )
        print(f"Reset {route_class} to phase={phase_of(0)} decision=cold_start")
    await pool.close()


if __name__ == "__main__":
    asyncio.run(trigger(sys.argv[1] if len(sys.argv) > 1 else "email_draft:standard"))

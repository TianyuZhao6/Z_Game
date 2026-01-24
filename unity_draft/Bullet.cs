using UnityEngine;

namespace ZGame.UnityDraft
{
    /// <summary>
    /// Simple bullet runtime model: position, velocity, distance cap, damage.
    /// Port effects (ricochet, pierce) later.
    /// </summary>
    public class Bullet : MonoBehaviour
    {
        public enum Faction
        {
            Player,
            Enemy,
            Neutral
        }
        public float damage = 10f;
        public float speed = 520f;
        public float maxDist = 600f;
        public Vector2 dir = Vector2.right;
        public bool alive = true;
        public string source = "player"; // extend as needed
        public Faction faction = Faction.Player;
        public int pierceLeft = 0;
        public int ricochetLeft = 0;
        public float hitRadius = 0f; // 0 => use system default
        public ICritSource attacker; // optional, for crit stats
        [Header("Ballistic")]
        public bool useGravity = false;
        public float gravity = -980f; // pixels per second^2 if you use pixel world; adjust as needed
        protected Vector2 _velocity;

        private Vector3 _spawnPos;

        private void OnEnable()
        {
            _spawnPos = transform.position;
            alive = true;
        }

        public virtual void Init(Vector3 pos, Vector2 direction, float dmg, float maxDistance, float spd)
        {
            transform.position = pos;
            _spawnPos = pos;
            dir = direction.normalized;
            damage = dmg;
            maxDist = maxDistance;
            speed = spd;
            alive = true;
            useGravity = false;
            gravity = -980f;
            _velocity = dir * speed;
            pierceLeft = 0;
            ricochetLeft = 0;
            source = "player";
            faction = Faction.Player;
            hitRadius = 0f;
            attacker = null;
        }

        /// <summary>
        /// Initialize a ballistic projectile with explicit velocity and gravity.
        /// </summary>
        public virtual void InitBallistic(Vector3 pos, Vector2 initialVelocity, float dmg, float maxDistance, float gravityAccel)
        {
            transform.position = pos;
            _spawnPos = pos;
            damage = dmg;
            maxDist = maxDistance;
            _velocity = initialVelocity;
            alive = true;
            useGravity = true;
            gravity = gravityAccel;
            pierceLeft = 0;
            ricochetLeft = 0;
            source = "player";
            faction = Faction.Player;
            hitRadius = 0f;
            attacker = null;
        }

        public void Tick(float dt)
        {
            if (!alive) return;
            if (useGravity)
            {
                _velocity.y += gravity * dt;
                transform.position += (Vector3)(_velocity * dt);
            }
            else
            {
                _velocity = dir * speed;
                transform.position += (Vector3)(dir * speed * dt);
            }
            float traveled = Vector3.Distance(transform.position, _spawnPos);
            if (traveled >= maxDist)
            {
                alive = false;
                gameObject.SetActive(false);
            }
        }
    }
}

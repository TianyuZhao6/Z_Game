using UnityEngine;

namespace ZGame.UnityDraft
{
    /// <summary>
    /// Simple bullet runtime model: position, velocity, distance cap, damage.
    /// Port effects (ricochet, pierce) later.
    /// </summary>
    public class Bullet : MonoBehaviour
    {
        public float damage = 10f;
        public float speed = 520f;
        public float maxDist = 600f;
        public Vector2 dir = Vector2.right;
        public bool alive = true;
        public string source = "player"; // extend as needed
        public int pierceLeft = 0;
        public int ricochetLeft = 0;
        public float hitRadius = 0f; // 0 => use system default
        public Player attacker; // optional, for crit stats

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
            pierceLeft = 0;
            ricochetLeft = 0;
            source = "player";
            hitRadius = 0f;
            attacker = null;
        }

        public void Tick(float dt)
        {
            if (!alive) return;
            transform.position += (Vector3)(dir * speed * dt);
            float traveled = Vector3.Distance(transform.position, _spawnPos);
            if (traveled >= maxDist)
            {
                alive = false;
                gameObject.SetActive(false);
            }
        }
    }
}

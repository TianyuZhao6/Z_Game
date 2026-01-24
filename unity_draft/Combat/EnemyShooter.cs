using UnityEngine;

namespace ZGame.UnityDraft.Combat
{
    /// <summary>
    /// Simple enemy firing hook: aims at player and fires on cooldown.
    /// Attach to enemies that have ranged attacks.
    /// </summary>
    public class EnemyShooter : MonoBehaviour
    {
        public GameBalanceConfig balance;
        public EnemyShotPool enemyShotPool;
        public BulletCombatSystem bulletSystem;
        public Transform target; // player transform
        private Enemy _enemy;

        [Header("Stats")]
        public float damage = 8f;
        public float speed = 420f;
        public float range = 520f;
        public float fireCooldown = 1.2f;
        [Tooltip("Allow friendly fire on shrapnel/explosive? If false, only player bullets trigger those effects.")]
        public bool allowFriendlyExplosive = false;

        private float _cd;

        private void Awake()
        {
            _enemy = GetComponent<Enemy>();
            if (balance != null)
            {
                // If this enemy has a config, pull ranged stats
                if (_enemy != null && _enemy.typeConfig != null)
                {
                    damage = _enemy.typeConfig.rangedDamage;
                    speed = _enemy.typeConfig.rangedSpeed;
                    range = _enemy.typeConfig.rangedRange;
                    fireCooldown = _enemy.typeConfig.rangedCooldown;
                }
            }
            if (target == null)
            {
                var p = FindObjectOfType<Player>();
                if (p != null) target = p.transform;
            }
        }

        private void Update()
        {
            _cd = Mathf.Max(0f, _cd - Time.deltaTime);
            if (_cd > 0f) return;
            if (!target) return;

            Vector2 dir = (target.position - transform.position);
            if (dir.sqrMagnitude <= 0.001f) return;
            dir.Normalize();

            var shot = enemyShotPool != null ? enemyShotPool.Get() as Bullet : null;
            if (shot == null && enemyShotPool == null && bulletSystem != null)
            {
                // fallback: try to get from a global BulletPool if present
                var pool = GetComponent<BulletPool>();
                if (pool != null) shot = pool.Get();
            }
            if (shot == null) return;
            shot.source = "enemy";
            shot.faction = Bullet.Faction.Enemy;
            shot.Init(transform.position, dir, damage, range, speed);
            shot.attacker = GetComponent<Enemy>();
            if (balance != null) shot.hitRadius = balance.enemyShotHitRadius;
            bulletSystem.RegisterBullet(shot);
            _cd = fireCooldown;
        }
    }
}

using UnityEngine;

namespace ZGame.UnityDraft.Combat
{
    /// <summary>
    /// Simple enemy firing hook: aims at player and fires on cooldown.
    /// Attach to enemies that have ranged attacks.
    /// </summary>
    public class EnemyShooter : MonoBehaviour
    {
        public enum FirePattern { Straight, Spread, LobArc }
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
        public float fireCooldownJitter = 0.25f;
        public FirePattern pattern = FirePattern.Straight;
        [Header("Spread")]
        public int spreadCount = 3;
        public float spreadArc = 30f;
        [Header("Lob")]
        public float lobUpBias = 0.35f;
        public float lobGravity = -980f;
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

            Fire(dir);
        }

        private void Fire(Vector2 dir)
        {
            switch (pattern)
            {
                case FirePattern.Spread:
                    FireSpread(dir);
                    break;
                case FirePattern.LobArc:
                    FireLob(dir);
                    break;
                default:
                    FireSingle(dir);
                    break;
            }
            float jitter = fireCooldownJitter > 0f ? Random.Range(-fireCooldownJitter, fireCooldownJitter) : 0f;
            _cd = Mathf.Max(0.1f, fireCooldown + jitter);
        }

        private Bullet GetShot()
        {
            Bullet shot = enemyShotPool != null ? enemyShotPool.Get() as Bullet : null;
            if (shot == null && enemyShotPool == null && bulletSystem != null)
            {
                var pool = GetComponent<BulletPool>();
                if (pool != null) shot = pool.Get();
            }
            return shot;
        }

        private void FireSingle(Vector2 dir)
        {
            var shot = GetShot();
            if (shot == null) return;
            shot.source = "enemy";
            shot.faction = Bullet.Faction.Enemy;
            shot.Init(transform.position, dir, damage, range, speed);
            shot.attacker = GetComponent<Enemy>();
            if (balance != null) shot.hitRadius = balance.enemyShotHitRadius;
            bulletSystem.RegisterBullet(shot);
        }

        private void FireSpread(Vector2 dir)
        {
            int count = Mathf.Max(1, spreadCount);
            float arc = spreadArc;
            float start = -arc * 0.5f;
            for (int i = 0; i < count; i++)
            {
                float t = count == 1 ? 0f : i / (float)(count - 1);
                float ang = start + arc * t;
                Vector2 d = Quaternion.Euler(0, 0, ang) * dir;
                FireSingle(d.normalized);
            }
        }

        private void FireLob(Vector2 dir)
        {
            var shot = GetShot();
            if (shot == null) return;
            shot.source = "enemy";
            shot.faction = Bullet.Faction.Enemy;
            Vector2 aim = (dir + Vector2.up * lobUpBias).normalized;
            Vector2 vel = aim * speed;
            shot.InitBallistic(transform.position, vel, damage, range, lobGravity);
            shot.attacker = GetComponent<Enemy>();
            if (balance != null) shot.hitRadius = balance.enemyShotHitRadius;
            bulletSystem.RegisterBullet(shot);
        }
    }
}

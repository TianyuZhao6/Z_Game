using UnityEngine;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Stationary turret enemy: aims at player, burst fires, rotates to nearest target.
    /// </summary>
    [RequireComponent(typeof(Combat.EnemyShooter))]
    public class TurretEnemy : MonoBehaviour
    {
        public float aimInterval = 0.2f;
        public float burstInterval = 2.5f;
        public int burstCount = 3;
        public float burstSpacing = 0.15f;
        public bool allowFriendlyFire = false;
        public float burstIntervalJitter = 0.35f;
        public enum TurretMode { Straight, Spread, ArcFan, Lob }
        public TurretMode mode = TurretMode.Straight;
        public float spreadArc = 45f;
        public int spreadCount = 5;
        public float arcFanStep = 12f;
        public float elementDamageMult = 1.0f;
        public float elementSpeedMult = 1.0f;

        private Combat.EnemyShooter _shooter;
        private Transform _target;
        private float _burstTimer;
        private float _aimTimer;

        private void Awake()
        {
            _shooter = GetComponent<Combat.EnemyShooter>();
            if (_shooter != null) _target = _shooter.target;
        }

        private void Update()
        {
            if (_shooter == null) return;
            _aimTimer -= Time.deltaTime;
            _burstTimer -= Time.deltaTime;
            if (_aimTimer <= 0f)
            {
                _aimTimer = aimInterval;
                if (_target == null)
                {
                    var p = FindObjectOfType<Player>();
                    if (p != null) _target = p.transform;
                    _shooter.target = _target;
                }
            }
            if (_burstTimer <= 0f)
            {
                float jitter = burstIntervalJitter != 0f ? Random.Range(-burstIntervalJitter, burstIntervalJitter) : 0f;
                _burstTimer = Mathf.Max(0.2f, burstInterval + jitter);
                StartCoroutine(Burst());
            }
        }

        private System.Collections.IEnumerator Burst()
        {
            float baseDmg = _shooter.damage;
            float baseSpd = _shooter.speed;
            _shooter.damage = baseDmg * elementDamageMult;
            _shooter.speed = baseSpd * elementSpeedMult;
            for (int i = 0; i < burstCount; i++)
            {
                _shooter.allowEnemyVsEnemy = allowFriendlyFire;
                _shooter.allowEnemyExplosive = allowFriendlyFire;
                _shooter.allowEnemyShrapnel = allowFriendlyFire;
                Vector2 baseDir = _shooter.target ? (_shooter.target.position - transform.position) : transform.right;
                if (baseDir.sqrMagnitude < 0.001f) baseDir = Vector2.right;
                baseDir.Normalize();

                // apply elemental tweaks
                _shooter.damage *= elementDamageMult;
                _shooter.speed *= elementSpeedMult;

                switch (mode)
                {
                    case TurretMode.Spread:
                        _shooter.pattern = Combat.EnemyShooter.FirePattern.Spread;
                        _shooter.spreadArc = spreadArc;
                        _shooter.spreadCount = spreadCount;
                        _shooter.SendMessage("Fire", baseDir, SendMessageOptions.DontRequireReceiver);
                        break;
                    case TurretMode.ArcFan:
                        _shooter.pattern = Combat.EnemyShooter.FirePattern.Straight;
                        int half = Mathf.Max(1, spreadCount);
                        for (int s = 0; s < half; s++)
                        {
                            float offset = (s - (half - 1) * 0.5f) * arcFanStep;
                            Vector2 dir = Quaternion.Euler(0, 0, offset) * baseDir;
                            _shooter.SendMessage("Fire", dir.normalized, SendMessageOptions.DontRequireReceiver);
                        }
                        break;
                    case TurretMode.Lob:
                        _shooter.pattern = Combat.EnemyShooter.FirePattern.LobArc;
                        _shooter.SendMessage("Fire", baseDir, SendMessageOptions.DontRequireReceiver);
                        break;
                    default:
                        _shooter.pattern = Combat.EnemyShooter.FirePattern.Straight;
                        _shooter.SendMessage("Fire", baseDir, SendMessageOptions.DontRequireReceiver);
                        break;
                }
                yield return new WaitForSeconds(burstSpacing);
            }
            _shooter.damage = baseDmg;
            _shooter.speed = baseSpd;
        }
    }
}

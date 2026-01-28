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
                _burstTimer = burstInterval;
                StartCoroutine(Burst());
            }
        }

        private System.Collections.IEnumerator Burst()
        {
            for (int i = 0; i < burstCount; i++)
            {
                _shooter.allowEnemyVsEnemy = allowFriendlyFire;
                _shooter.allowEnemyExplosive = allowFriendlyFire;
                _shooter.allowEnemyShrapnel = allowFriendlyFire;
                // Fire once
                var dir = _shooter.target ? (_shooter.target.position - transform.position).normalized : transform.right;
                _shooter.pattern = Combat.EnemyShooter.FirePattern.Straight;
                _shooter.SendMessage("Fire", dir, SendMessageOptions.DontRequireReceiver);
                yield return new WaitForSeconds(burstSpacing);
            }
        }
    }
}

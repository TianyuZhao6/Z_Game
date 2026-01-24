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
        public BulletPool bulletPool;
        public BulletCombatSystem bulletSystem;
        public Transform target; // player transform

        [Header("Stats")]
        public float damage = 8f;
        public float speed = 420f;
        public float range = 520f;
        public float fireCooldown = 1.2f;

        private float _cd;

        private void Update()
        {
            _cd = Mathf.Max(0f, _cd - Time.deltaTime);
            if (_cd > 0f) return;
            if (!target) return;

            Vector2 dir = (target.position - transform.position);
            if (dir.sqrMagnitude <= 0.001f) return;
            dir.Normalize();

            var shot = bulletPool.Get();
            shot.source = "enemy";
            shot.Init(transform.position, dir, damage, range, speed);
            bulletSystem.RegisterBullet(shot);
            _cd = fireCooldown;
        }
    }
}

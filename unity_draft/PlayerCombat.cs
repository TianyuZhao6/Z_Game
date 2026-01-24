using UnityEngine;
using ZGame.UnityDraft.Combat;

namespace ZGame.UnityDraft
{
    /// <summary>
    /// Handles firing bullets for the player; hook to input and aim direction.
    /// </summary>
    public class PlayerCombat : MonoBehaviour
    {
        public GameBalanceConfig balance;
        public BulletPool bulletPool;
        public BulletCombatSystem bulletSystem;
        public Player player;

        [Tooltip("Damage per shot; can be overridden by upgrades.")]
        public float bulletDamage = 10f;
        [Tooltip("Bullet speed.")]
        public float bulletSpeed = 520f;
        [Tooltip("Starting pierce charges per bullet.")]
        public int bulletPierce = 0;
        [Tooltip("Starting ricochet charges per bullet.")]
        public int bulletRicochet = 0;

        private void Awake()
        {
            if (player == null) player = GetComponent<Player>();
        }

        public void TryFire(Vector2 aimDir)
        {
            if (player == null || bulletPool == null || bulletSystem == null) return;
            if (!player.CanFire()) return;
            aimDir = aimDir.sqrMagnitude < 0.001f ? Vector2.right : aimDir.normalized;

            var b = bulletPool.Get();
            b.Init(transform.position, aimDir, bulletDamage, player.CurrentRange(), bulletSpeed);
            b.pierceLeft = bulletPierce;
            b.ricochetLeft = bulletRicochet;
            b.attacker = player;
            b.faction = Bullet.Faction.Player;
            bulletSystem.RegisterBullet(b);
            player.ConsumeFireCd();
        }

        private void Update()
        {
            if (player != null)
            {
                player.TickFireCd(Time.deltaTime);
            }
        }
    }
}

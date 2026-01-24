using UnityEngine;

namespace ZGame.UnityDraft
{
    /// <summary>
    /// Minimal player runtime state aligned with ZGame.py fields.
    /// </summary>
    public class Player : MonoBehaviour
    {
        public GameBalanceConfig balance;

        [Header("Stats")]
        public int maxHp = 40;
        public int hp = 40;
        public float speed = 4.5f;
        public float rangeBase = 260f; // BULLET_SPACING_PX reference; adjust once mapped
        public float rangeMult = 1f;
        public float fireCooldown = 0.35f;
        public float fireCdTimer = 0f;
        public int attack = 10;
        public int shieldHp = 0; // placeholder for shield routing
        public float critChance = 0.05f;
        public float critMult = 1.8f;

        [Header("Runtime")]
        public float radiusPx;
        public int xp;
        public int level = 1;

        private void Awake()
        {
            if (balance != null)
            {
                speed = balance.playerSpeed;
                radiusPx = balance.playerRadius * balance.cellSize;
            }
        }

        public float CurrentRange() => rangeBase * rangeMult;

        public void Damage(int dmg)
        {
            hp = Mathf.Max(0, hp - Mathf.Max(0, dmg));
        }

        public void TickFireCd(float dt)
        {
            fireCdTimer = Mathf.Max(0f, fireCdTimer - dt);
        }

        public bool CanFire() => fireCdTimer <= 0f;

        public void ConsumeFireCd() => fireCdTimer = fireCooldown;
    }
}

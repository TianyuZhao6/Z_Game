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
        public float bonePlatingHp = 0f;
        public float carapaceHp = 0f;
        public float critChance = 0.05f;
        public float critMult = 1.8f;
        public float slowResist = 0f; // 0..1 reduces incoming slows

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
            var status = GetComponent<Systems.StatusEffect>();
            if (status != null) status.TryAbsorb(ref dmg);
            hp = Mathf.Max(0, hp - Mathf.Max(0, dmg));
        }

        public void ApplyBonePlating(float hpValue)
        {
            Systems.StatusEffect.ApplyBonePlating(gameObject, hpValue);
        }

        public void ApplyCarapace(float hpValue)
        {
            Systems.StatusEffect.ApplyCarapace(gameObject, hpValue);
        }

        public void ApplySlowResist(float amount)
        {
            slowResist = Mathf.Clamp01(amount);
        }

        public void TickFireCd(float dt)
        {
            fireCdTimer = Mathf.Max(0f, fireCdTimer - dt);
        }

        public bool CanFire() => fireCdTimer <= 0f;

        public void ConsumeFireCd() => fireCdTimer = fireCooldown;
    }
}

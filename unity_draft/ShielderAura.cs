using UnityEngine;

namespace ZGame.UnityDraft
{
    /// <summary>
    /// Shielder-style aura that grants shields to nearby enemies on a cooldown.
    /// Attach to shielder prefabs.
    /// </summary>
    public class ShielderAura : MonoBehaviour
    {
        public GameBalanceConfig balance;
        public LayerMask enemyMask;
        public float shieldDuration = 5f;

        private float _cd;

        private void Awake()
        {
            if (balance != null && enemyMask == 0)
            {
                enemyMask = LayerMask.GetMask("Enemy");
            }
            _cd = 0f;
            if (balance != null)
            {
                shieldDuration = balance.shielderShieldDuration;
            }
        }

        private void Update()
        {
            if (balance == null) return;
            _cd = Mathf.Max(0f, _cd - Time.deltaTime);
            if (_cd > 0f) return;
            ApplyShield();
            _cd = balance.shielderCooldown;
        }

        private void ApplyShield()
        {
            float radius = balance.shielderRadius;
            int amount = balance.shielderShieldAmount;
            Collider2D[] hits = Physics2D.OverlapCircleAll(transform.position, radius, enemyMask);
            foreach (var h in hits)
            {
                var e = h.GetComponentInParent<Enemy>();
                if (e == null || !e.gameObject.activeSelf) continue;
                e.shieldHp = Mathf.Max(e.shieldHp, amount);
                // Track duration per enemy
                var timed = e.GetComponent<TimedShield>();
                if (timed == null)
                {
                    timed = e.gameObject.AddComponent<TimedShield>();
                }
                timed.SetShield(amount, shieldDuration);
            }
        }
    }
}

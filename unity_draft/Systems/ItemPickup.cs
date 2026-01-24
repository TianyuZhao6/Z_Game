using UnityEngine;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Generic item pickup: applies simple effects to player/meta and then disables/destroys itself.
    /// Extend with ScriptableObjects for real items later.
    /// </summary>
    [RequireComponent(typeof(Collider2D))]
    public class ItemPickup : MonoBehaviour
    {
        public enum ItemType { Heal, Speed, Range, Shield, Coupon, Consumable }
        public ItemType type = ItemType.Heal;
        public int amount = 10;
        public string consumableId;
        public int consumableCount = 1;
        public MetaProgression meta;
        [Header("FX")]
        public GameObject pickupVfx;
        public AudioClip pickupSfx;

        private void OnTriggerEnter2D(Collider2D other)
        {
            var player = other.GetComponentInParent<Player>();
            if (player == null) return;
            Apply(player);
            if (pickupVfx != null)
            {
                var v = Instantiate(pickupVfx, transform.position, Quaternion.identity);
                v.SetActive(true);
            }
            if (pickupSfx != null)
            {
                AudioSource.PlayClipAtPoint(pickupSfx, transform.position);
            }
            gameObject.SetActive(false);
        }

        private void Apply(Player player)
        {
            switch (type)
            {
                case ItemType.Heal:
                    player.hp = Mathf.Min(player.maxHp, player.hp + amount);
                    break;
                case ItemType.Speed:
                    player.speed += amount * 0.01f;
                    break;
                case ItemType.Range:
                    player.rangeMult += amount * 0.01f;
                    break;
                case ItemType.Shield:
                    player.shieldHp = Mathf.Max(player.shieldHp, amount);
                    break;
                case ItemType.Coupon:
                    meta?.AddCoupon(amount);
                    break;
                case ItemType.Consumable:
                    if (meta != null && !string.IsNullOrEmpty(consumableId))
                    {
                        meta.AddConsumable(consumableId, Mathf.Max(1, consumableCount));
                    }
                    break;
            }
        }
    }
}

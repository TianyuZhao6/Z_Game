using UnityEngine;

namespace ZGame.UnityDraft.VFX
{
    /// <summary>
    /// Simple pooled explosion VFX. Hook this into TriggerExplosive when you add pooling/instantiation.
    /// </summary>
    public class ExplosionVFX : MonoBehaviour
    {
        public float life = 0.4f;
        private float _t;

        private void OnEnable()
        {
            _t = 0f;
        }

        private void Update()
        {
            _t += Time.deltaTime;
            if (_t >= life)
            {
                gameObject.SetActive(false);
            }
        }
    }
}

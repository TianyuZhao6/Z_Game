Shader "Unlit/FogMask"
{
    Properties
    {
        _FogColor ("Fog Color", Color) = (0,0,0,0.8)
        _Radius ("Radius", Range(0,1)) = 0.3
        _Softness ("Softness", Range(0,0.5)) = 0.15
        _Center ("Center", Vector) = (0.5,0.5,0,0)
    }
    SubShader
    {
        Tags { "RenderType"="Transparent" "Queue"="Transparent" }
        LOD 100
        ZWrite Off
        Blend SrcAlpha OneMinusSrcAlpha

        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"

            struct appdata
            {
                float4 vertex : POSITION;
                float2 uv : TEXCOORD0;
            };

            struct v2f
            {
                float4 vertex : SV_POSITION;
                float2 uv : TEXCOORD0;
            };

            fixed4 _FogColor;
            float _Radius;
            float _Softness;
            float4 _Center;

            v2f vert (appdata v)
            {
                v2f o;
                o.vertex = UnityObjectToClipPos(v.vertex);
                o.uv = v.uv;
                return o;
            }

            fixed4 frag (v2f i) : SV_Target
            {
                float2 uv = i.uv;
                float d = distance(uv, _Center.xy);
                float alpha = smoothstep(_Radius, _Radius - _Softness, d);
                return fixed4(_FogColor.rgb, _FogColor.a * alpha);
            }
            ENDCG
        }
    }
}

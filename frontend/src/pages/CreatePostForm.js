import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Calendar } from '@/components/ui/calendar';
import { toast } from 'sonner';
import axios from 'axios';
import Cropper from 'react-easy-crop';
import { getSocialAccounts, uploadMedia, generateImage, getHashtagGroups, generateContent } from '@/lib/api';
import {
  FaTwitter, FaInstagram, FaLinkedin, FaFacebook,
  FaTiktok, FaYoutube, FaPinterest, FaArrowLeft,
  FaEye, FaEyeSlash, FaInfoCircle, FaClock, FaTimes,
  FaChevronUp, FaChevronDown, FaMagic, FaRobot, FaDiscord,
} from 'react-icons/fa';
import { SiBluesky, SiThreads } from 'react-icons/si';

import AccountSelector from '@/components/composer/AccountSelector';
import PlatformEditor from '@/components/composer/PlatformEditor';
import PreviewPanel from '@/components/composer/previews/PreviewPanel';

// ── Timezone list (comprehensive IANA) ────────────────────────────────────────
const TIMEZONES = [
  // UTC-12
  { value: 'Etc/GMT+12',                      label: 'GMT-12   International Date Line West' },
  // UTC-11
  { value: 'Pacific/Pago_Pago',               label: 'GMT-11   Pago Pago, American Samoa' },
  { value: 'Pacific/Midway',                  label: 'GMT-11   Midway Island' },
  { value: 'Pacific/Niue',                    label: 'GMT-11   Niue' },
  // UTC-10
  { value: 'Pacific/Honolulu',                label: 'GMT-10   Honolulu, Hawaii' },
  { value: 'Pacific/Tahiti',                  label: 'GMT-10   Tahiti, French Polynesia' },
  { value: 'Pacific/Rarotonga',               label: 'GMT-10   Rarotonga, Cook Islands' },
  // UTC-9:30
  { value: 'Pacific/Marquesas',               label: 'GMT-9:30  Marquesas Islands' },
  // UTC-9
  { value: 'America/Anchorage',               label: 'GMT-9    Anchorage, Alaska' },
  { value: 'America/Juneau',                  label: 'GMT-9    Juneau, Alaska' },
  { value: 'Pacific/Gambier',                 label: 'GMT-9    Gambier Islands' },
  // UTC-8
  { value: 'America/Los_Angeles',             label: 'GMT-8    Los Angeles, Seattle, Vancouver (Pacific)' },
  { value: 'America/Tijuana',                 label: 'GMT-8    Tijuana, Baja California' },
  { value: 'America/Vancouver',               label: 'GMT-8    Vancouver, British Columbia' },
  // UTC-7
  { value: 'America/Denver',                  label: 'GMT-7    Denver, Salt Lake City (Mountain)' },
  { value: 'America/Phoenix',                 label: 'GMT-7    Phoenix, Arizona (no DST)' },
  { value: 'America/Edmonton',                label: 'GMT-7    Edmonton, Alberta' },
  { value: 'America/Chihuahua',               label: 'GMT-7    Chihuahua, Mazatlán' },
  // UTC-6
  { value: 'America/Chicago',                 label: 'GMT-6    Chicago, Dallas, Houston (Central)' },
  { value: 'America/Winnipeg',                label: 'GMT-6    Winnipeg, Manitoba' },
  { value: 'America/Mexico_City',             label: 'GMT-6    Mexico City, Guadalajara' },
  { value: 'America/Guatemala',               label: 'GMT-6    Guatemala City' },
  { value: 'America/Costa_Rica',              label: 'GMT-6    San José, Costa Rica' },
  { value: 'America/El_Salvador',             label: 'GMT-6    San Salvador, El Salvador' },
  { value: 'America/Tegucigalpa',             label: 'GMT-6    Tegucigalpa, Honduras' },
  { value: 'America/Managua',                 label: 'GMT-6    Managua, Nicaragua' },
  // UTC-5
  { value: 'America/New_York',                label: 'GMT-5    New York, Miami, Toronto (Eastern)' },
  { value: 'America/Toronto',                 label: 'GMT-5    Toronto, Ottawa' },
  { value: 'America/Montreal',                label: 'GMT-5    Montréal, Quebec' },
  { value: 'America/Havana',                  label: 'GMT-5    Havana, Cuba' },
  { value: 'America/Jamaica',                 label: 'GMT-5    Kingston, Jamaica' },
  { value: 'America/Panama',                  label: 'GMT-5    Panama City' },
  { value: 'America/Bogota',                  label: 'GMT-5    Bogotá, Colombia' },
  { value: 'America/Lima',                    label: 'GMT-5    Lima, Peru' },
  { value: 'America/Guayaquil',               label: 'GMT-5    Quito, Ecuador' },
  { value: 'America/Port-au-Prince',          label: 'GMT-5    Port-au-Prince, Haiti' },
  // UTC-4:30
  { value: 'America/Caracas',                 label: 'GMT-4:30  Caracas, Venezuela' },
  // UTC-4
  { value: 'America/Halifax',                 label: 'GMT-4    Halifax, Atlantic Canada' },
  { value: 'America/Santo_Domingo',           label: 'GMT-4    Santo Domingo, Dominican Republic' },
  { value: 'America/Puerto_Rico',             label: 'GMT-4    San Juan, Puerto Rico' },
  { value: 'America/Barbados',                label: 'GMT-4    Bridgetown, Barbados' },
  { value: 'America/Port_of_Spain',           label: 'GMT-4    Port of Spain, Trinidad & Tobago' },
  { value: 'America/Manaus',                  label: 'GMT-4    Manaus, Brazil (Amazonas)' },
  { value: 'America/La_Paz',                  label: 'GMT-4    La Paz, Bolivia' },
  { value: 'America/Santiago',                label: 'GMT-4    Santiago, Chile' },
  { value: 'America/Asuncion',                label: 'GMT-4    Asunción, Paraguay' },
  { value: 'America/Guyana',                  label: 'GMT-4    Georgetown, Guyana' },
  // UTC-3:30
  { value: 'America/St_Johns',                label: 'GMT-3:30  St. John\'s, Newfoundland' },
  // UTC-3
  { value: 'America/Sao_Paulo',               label: 'GMT-3    São Paulo, Rio de Janeiro' },
  { value: 'America/Argentina/Buenos_Aires',  label: 'GMT-3    Buenos Aires, Argentina' },
  { value: 'America/Montevideo',              label: 'GMT-3    Montevideo, Uruguay' },
  { value: 'America/Cayenne',                 label: 'GMT-3    Cayenne, French Guiana' },
  { value: 'America/Paramaribo',              label: 'GMT-3    Paramaribo, Suriname' },
  { value: 'America/Nuuk',                    label: 'GMT-3    Nuuk, Greenland' },
  { value: 'Atlantic/Stanley',                label: 'GMT-3    Stanley, Falkland Islands' },
  // UTC-2
  { value: 'America/Noronha',                 label: 'GMT-2    Fernando de Noronha, Brazil' },
  { value: 'Atlantic/South_Georgia',          label: 'GMT-2    South Georgia' },
  // UTC-1
  { value: 'Atlantic/Azores',                 label: 'GMT-1    Azores, Portugal' },
  { value: 'Atlantic/Cape_Verde',             label: 'GMT-1    Praia, Cape Verde' },
  // UTC+0
  { value: 'UTC',                             label: 'GMT+0    UTC / Coordinated Universal Time' },
  { value: 'Europe/London',                   label: 'GMT+0    London, Edinburgh (UK)' },
  { value: 'Europe/Dublin',                   label: 'GMT+0    Dublin, Ireland' },
  { value: 'Europe/Lisbon',                   label: 'GMT+0    Lisbon, Portugal' },
  { value: 'Atlantic/Reykjavik',              label: 'GMT+0    Reykjavik, Iceland' },
  { value: 'Africa/Casablanca',               label: 'GMT+0    Casablanca, Morocco' },
  { value: 'Africa/Accra',                    label: 'GMT+0    Accra, Ghana' },
  { value: 'Africa/Abidjan',                  label: 'GMT+0    Abidjan, Côte d\'Ivoire' },
  { value: 'Africa/Dakar',                    label: 'GMT+0    Dakar, Senegal' },
  { value: 'Africa/Monrovia',                 label: 'GMT+0    Monrovia, Liberia' },
  // UTC+1
  { value: 'Europe/Paris',                    label: 'GMT+1    Paris, France' },
  { value: 'Europe/Berlin',                   label: 'GMT+1    Berlin, Germany' },
  { value: 'Europe/Madrid',                   label: 'GMT+1    Madrid, Barcelona, Spain' },
  { value: 'Europe/Rome',                     label: 'GMT+1    Rome, Milan, Italy' },
  { value: 'Europe/Amsterdam',                label: 'GMT+1    Amsterdam, Netherlands' },
  { value: 'Europe/Brussels',                 label: 'GMT+1    Brussels, Belgium' },
  { value: 'Europe/Stockholm',                label: 'GMT+1    Stockholm, Sweden' },
  { value: 'Europe/Oslo',                     label: 'GMT+1    Oslo, Norway' },
  { value: 'Europe/Copenhagen',               label: 'GMT+1    Copenhagen, Denmark' },
  { value: 'Europe/Warsaw',                   label: 'GMT+1    Warsaw, Poland' },
  { value: 'Europe/Vienna',                   label: 'GMT+1    Vienna, Austria' },
  { value: 'Europe/Budapest',                 label: 'GMT+1    Budapest, Hungary' },
  { value: 'Europe/Prague',                   label: 'GMT+1    Prague, Czech Republic' },
  { value: 'Europe/Zurich',                   label: 'GMT+1    Zürich, Switzerland' },
  { value: 'Europe/Zagreb',                   label: 'GMT+1    Zagreb, Croatia' },
  { value: 'Europe/Belgrade',                 label: 'GMT+1    Belgrade, Serbia' },
  { value: 'Europe/Bratislava',               label: 'GMT+1    Bratislava, Slovakia' },
  { value: 'Europe/Ljubljana',                label: 'GMT+1    Ljubljana, Slovenia' },
  { value: 'Europe/Sarajevo',                 label: 'GMT+1    Sarajevo, Bosnia' },
  { value: 'Europe/Skopje',                   label: 'GMT+1    Skopje, North Macedonia' },
  { value: 'Africa/Lagos',                    label: 'GMT+1    Lagos, Nigeria' },
  { value: 'Africa/Tunis',                    label: 'GMT+1    Tunis, Tunisia' },
  { value: 'Africa/Algiers',                  label: 'GMT+1    Algiers, Algeria' },
  { value: 'Africa/Douala',                   label: 'GMT+1    Douala, Cameroon' },
  { value: 'Africa/Brazzaville',              label: 'GMT+1    Brazzaville, Republic of Congo' },
  { value: 'Africa/Kinshasa',                 label: 'GMT+1    Kinshasa, DR Congo (West)' },
  // UTC+2
  { value: 'Europe/Athens',                   label: 'GMT+2    Athens, Greece' },
  { value: 'Europe/Helsinki',                 label: 'GMT+2    Helsinki, Finland' },
  { value: 'Europe/Kyiv',                     label: 'GMT+2    Kyiv, Ukraine' },
  { value: 'Europe/Bucharest',                label: 'GMT+2    Bucharest, Romania' },
  { value: 'Europe/Sofia',                    label: 'GMT+2    Sofia, Bulgaria' },
  { value: 'Europe/Riga',                     label: 'GMT+2    Riga, Latvia' },
  { value: 'Europe/Tallinn',                  label: 'GMT+2    Tallinn, Estonia' },
  { value: 'Europe/Vilnius',                  label: 'GMT+2    Vilnius, Lithuania' },
  { value: 'Asia/Jerusalem',                  label: 'GMT+2    Jerusalem, Tel Aviv, Israel' },
  { value: 'Asia/Beirut',                     label: 'GMT+2    Beirut, Lebanon' },
  { value: 'Asia/Amman',                      label: 'GMT+2    Amman, Jordan' },
  { value: 'Asia/Damascus',                   label: 'GMT+2    Damascus, Syria' },
  { value: 'Asia/Nicosia',                    label: 'GMT+2    Nicosia, Cyprus' },
  { value: 'Africa/Cairo',                    label: 'GMT+2    Cairo, Egypt' },
  { value: 'Africa/Johannesburg',             label: 'GMT+2    Johannesburg, Cape Town, South Africa' },
  { value: 'Africa/Harare',                   label: 'GMT+2    Harare, Zimbabwe' },
  { value: 'Africa/Maputo',                   label: 'GMT+2    Maputo, Mozambique' },
  { value: 'Africa/Lusaka',                   label: 'GMT+2    Lusaka, Zambia' },
  { value: 'Africa/Tripoli',                  label: 'GMT+2    Tripoli, Libya' },
  { value: 'Africa/Lubumbashi',               label: 'GMT+2    Lubumbashi, DR Congo (East)' },
  { value: 'Africa/Gaborone',                 label: 'GMT+2    Gaborone, Botswana' },
  { value: 'Africa/Blantyre',                 label: 'GMT+2    Blantyre, Malawi' },
  // UTC+3
  { value: 'Europe/Moscow',                   label: 'GMT+3    Moscow, St. Petersburg, Russia' },
  { value: 'Europe/Istanbul',                 label: 'GMT+3    Istanbul, Ankara, Turkey' },
  { value: 'Europe/Minsk',                    label: 'GMT+3    Minsk, Belarus' },
  { value: 'Asia/Riyadh',                     label: 'GMT+3    Riyadh, Jeddah, Saudi Arabia' },
  { value: 'Asia/Kuwait',                     label: 'GMT+3    Kuwait City' },
  { value: 'Asia/Baghdad',                    label: 'GMT+3    Baghdad, Iraq' },
  { value: 'Asia/Qatar',                      label: 'GMT+3    Doha, Qatar' },
  { value: 'Asia/Bahrain',                    label: 'GMT+3    Manama, Bahrain' },
  { value: 'Asia/Aden',                       label: 'GMT+3    Aden, Yemen' },
  { value: 'Africa/Nairobi',                  label: 'GMT+3    Nairobi, Kenya' },
  { value: 'Africa/Addis_Ababa',              label: 'GMT+3    Addis Ababa, Ethiopia' },
  { value: 'Africa/Mogadishu',                label: 'GMT+3    Mogadishu, Somalia' },
  { value: 'Africa/Dar_es_Salaam',            label: 'GMT+3    Dar es Salaam, Tanzania' },
  { value: 'Africa/Kampala',                  label: 'GMT+3    Kampala, Uganda' },
  { value: 'Africa/Khartoum',                 label: 'GMT+3    Khartoum, Sudan' },
  { value: 'Africa/Djibouti',                 label: 'GMT+3    Djibouti' },
  { value: 'Indian/Antananarivo',             label: 'GMT+3    Antananarivo, Madagascar' },
  { value: 'Indian/Comoro',                   label: 'GMT+3    Moroni, Comoros' },
  // UTC+3:30
  { value: 'Asia/Tehran',                     label: 'GMT+3:30  Tehran, Iran' },
  // UTC+4
  { value: 'Asia/Dubai',                      label: 'GMT+4    Dubai, UAE' },
  { value: 'Asia/Muscat',                     label: 'GMT+4    Muscat, Oman' },
  { value: 'Asia/Baku',                       label: 'GMT+4    Baku, Azerbaijan' },
  { value: 'Asia/Tbilisi',                    label: 'GMT+4    Tbilisi, Georgia' },
  { value: 'Asia/Yerevan',                    label: 'GMT+4    Yerevan, Armenia' },
  { value: 'Indian/Mauritius',                label: 'GMT+4    Port Louis, Mauritius' },
  { value: 'Indian/Reunion',                  label: 'GMT+4    Réunion' },
  { value: 'Indian/Mahe',                     label: 'GMT+4    Mahé, Seychelles' },
  { value: 'Europe/Samara',                   label: 'GMT+4    Samara, Russia' },
  // UTC+4:30
  { value: 'Asia/Kabul',                      label: 'GMT+4:30  Kabul, Afghanistan' },
  // UTC+5
  { value: 'Asia/Karachi',                    label: 'GMT+5    Karachi, Islamabad, Pakistan' },
  { value: 'Asia/Tashkent',                   label: 'GMT+5    Tashkent, Uzbekistan' },
  { value: 'Asia/Samarkand',                  label: 'GMT+5    Samarkand, Uzbekistan' },
  { value: 'Asia/Dushanbe',                   label: 'GMT+5    Dushanbe, Tajikistan' },
  { value: 'Asia/Ashgabat',                   label: 'GMT+5    Ashgabat, Turkmenistan' },
  { value: 'Asia/Yekaterinburg',              label: 'GMT+5    Yekaterinburg, Russia' },
  { value: 'Indian/Maldives',                 label: 'GMT+5    Malé, Maldives' },
  // UTC+5:30
  { value: 'Asia/Kolkata',                    label: 'GMT+5:30  Mumbai, Delhi, Kolkata, Chennai (India)' },
  { value: 'Asia/Colombo',                    label: 'GMT+5:30  Colombo, Sri Lanka' },
  // UTC+5:45
  { value: 'Asia/Kathmandu',                  label: 'GMT+5:45  Kathmandu, Nepal' },
  // UTC+6
  { value: 'Asia/Dhaka',                      label: 'GMT+6    Dhaka, Bangladesh' },
  { value: 'Asia/Almaty',                     label: 'GMT+6    Almaty, Kazakhstan' },
  { value: 'Asia/Bishkek',                    label: 'GMT+6    Bishkek, Kyrgyzstan' },
  { value: 'Asia/Novosibirsk',                label: 'GMT+6    Novosibirsk, Russia' },
  { value: 'Indian/Chagos',                   label: 'GMT+6    Chagos (British Indian Ocean Territory)' },
  // UTC+6:30
  { value: 'Asia/Yangon',                     label: 'GMT+6:30  Yangon, Myanmar (Burma)' },
  { value: 'Indian/Cocos',                    label: 'GMT+6:30  Cocos (Keeling) Islands' },
  // UTC+7
  { value: 'Asia/Bangkok',                    label: 'GMT+7    Bangkok, Thailand' },
  { value: 'Asia/Jakarta',                    label: 'GMT+7    Jakarta, Indonesia (West)' },
  { value: 'Asia/Ho_Chi_Minh',               label: 'GMT+7    Ho Chi Minh City, Hanoi, Vietnam' },
  { value: 'Asia/Phnom_Penh',                label: 'GMT+7    Phnom Penh, Cambodia' },
  { value: 'Asia/Vientiane',                  label: 'GMT+7    Vientiane, Laos' },
  { value: 'Asia/Krasnoyarsk',               label: 'GMT+7    Krasnoyarsk, Russia' },
  { value: 'Indian/Christmas',               label: 'GMT+7    Christmas Island' },
  // UTC+8
  { value: 'Asia/Shanghai',                   label: 'GMT+8    Beijing, Shanghai, China' },
  { value: 'Asia/Hong_Kong',                  label: 'GMT+8    Hong Kong' },
  { value: 'Asia/Taipei',                     label: 'GMT+8    Taipei, Taiwan' },
  { value: 'Asia/Singapore',                  label: 'GMT+8    Singapore' },
  { value: 'Asia/Kuala_Lumpur',               label: 'GMT+8    Kuala Lumpur, Malaysia' },
  { value: 'Asia/Manila',                     label: 'GMT+8    Manila, Philippines' },
  { value: 'Asia/Makassar',                   label: 'GMT+8    Makassar, Indonesia (Central)' },
  { value: 'Asia/Brunei',                     label: 'GMT+8    Bandar Seri Begawan, Brunei' },
  { value: 'Australia/Perth',                 label: 'GMT+8    Perth, Western Australia' },
  { value: 'Asia/Ulaanbaatar',               label: 'GMT+8    Ulaanbaatar, Mongolia' },
  { value: 'Asia/Irkutsk',                    label: 'GMT+8    Irkutsk, Russia' },
  // UTC+8:45
  { value: 'Australia/Eucla',                 label: 'GMT+8:45  Eucla, Australia' },
  // UTC+9
  { value: 'Asia/Tokyo',                      label: 'GMT+9    Tokyo, Osaka, Japan' },
  { value: 'Asia/Seoul',                      label: 'GMT+9    Seoul, Busan, South Korea' },
  { value: 'Asia/Pyongyang',                  label: 'GMT+9    Pyongyang, North Korea' },
  { value: 'Asia/Jayapura',                   label: 'GMT+9    Jayapura, Indonesia (East)' },
  { value: 'Pacific/Palau',                   label: 'GMT+9    Ngerulmud, Palau' },
  { value: 'Asia/Yakutsk',                    label: 'GMT+9    Yakutsk, Russia' },
  // UTC+9:30
  { value: 'Australia/Adelaide',              label: 'GMT+9:30  Adelaide, South Australia' },
  { value: 'Australia/Darwin',                label: 'GMT+9:30  Darwin, Northern Territory' },
  // UTC+10
  { value: 'Australia/Sydney',                label: 'GMT+10   Sydney, Melbourne, Canberra' },
  { value: 'Australia/Brisbane',              label: 'GMT+10   Brisbane, Queensland (no DST)' },
  { value: 'Australia/Hobart',                label: 'GMT+10   Hobart, Tasmania' },
  { value: 'Pacific/Port_Moresby',            label: 'GMT+10   Port Moresby, Papua New Guinea' },
  { value: 'Pacific/Guam',                    label: 'GMT+10   Hagåtña, Guam' },
  { value: 'Pacific/Saipan',                  label: 'GMT+10   Saipan, Northern Mariana Islands' },
  { value: 'Pacific/Chuuk',                   label: 'GMT+10   Chuuk, Federated States of Micronesia' },
  { value: 'Asia/Vladivostok',                label: 'GMT+10   Vladivostok, Russia' },
  // UTC+10:30
  { value: 'Australia/Lord_Howe',             label: 'GMT+10:30  Lord Howe Island, Australia' },
  // UTC+11
  { value: 'Pacific/Guadalcanal',             label: 'GMT+11   Honiara, Solomon Islands' },
  { value: 'Pacific/Noumea',                  label: 'GMT+11   Nouméa, New Caledonia' },
  { value: 'Pacific/Efate',                   label: 'GMT+11   Port Vila, Vanuatu' },
  { value: 'Pacific/Pohnpei',                 label: 'GMT+11   Pohnpei, Micronesia' },
  { value: 'Pacific/Norfolk',                 label: 'GMT+11   Kingston, Norfolk Island' },
  { value: 'Asia/Magadan',                    label: 'GMT+11   Magadan, Russia' },
  { value: 'Asia/Sakhalin',                   label: 'GMT+11   Yuzhno-Sakhalinsk, Russia' },
  // UTC+12
  { value: 'Pacific/Auckland',                label: 'GMT+12   Auckland, Wellington, New Zealand' },
  { value: 'Pacific/Fiji',                    label: 'GMT+12   Suva, Fiji' },
  { value: 'Pacific/Tarawa',                  label: 'GMT+12   Tarawa, Kiribati (Gilbert Islands)' },
  { value: 'Pacific/Majuro',                  label: 'GMT+12   Majuro, Marshall Islands' },
  { value: 'Pacific/Nauru',                   label: 'GMT+12   Yaren, Nauru' },
  { value: 'Pacific/Funafuti',                label: 'GMT+12   Funafuti, Tuvalu' },
  { value: 'Pacific/Wallis',                  label: 'GMT+12   Wallis and Futuna' },
  { value: 'Asia/Kamchatka',                  label: 'GMT+12   Petropavlovsk-Kamchatsky, Russia' },
  // UTC+12:45
  { value: 'Pacific/Chatham',                 label: 'GMT+12:45  Chatham Islands, New Zealand' },
  // UTC+13
  { value: 'Pacific/Apia',                    label: 'GMT+13   Apia, Samoa (Western Samoa)' },
  { value: 'Pacific/Tongatapu',               label: 'GMT+13   Nuku\'alofa, Tonga' },
  { value: 'Pacific/Fakaofo',                 label: 'GMT+13   Fakaofo, Tokelau' },
  // UTC+14
  { value: 'Pacific/Kiritimati',              label: 'GMT+14   Kiritimati (Christmas Island), Kiribati' },
];

// Convert a local date+time string in a specific timezone to UTC ISO string
const localToUTC = (dateStr, timeStr, timezone) => {
  const fakeUTC = new Date(`${dateStr}T${timeStr}:00Z`);
  const localStr = fakeUTC.toLocaleString('en-US', { timeZone: timezone });
  const localAsUTC = new Date(localStr + ' UTC');
  const offsetMs = localAsUTC - fakeUTC;
  return new Date(fakeUTC.getTime() - offsetMs).toISOString();
};

// Format 24h "HH:MM" → "h:MM AM/PM"
const fmt12h = (t24) => {
  if (!t24) return '';
  const [h, m] = t24.split(':').map(Number);
  const ampm = h < 12 ? 'AM' : 'PM';
  const h12  = h % 12 || 12;
  return `${h12}:${String(m).padStart(2, '0')} ${ampm}`;
};

// ── Platform icon map ─────────────────────────────────────────────────────────
const platformIcons = {
  facebook:  { icon: FaFacebook,  color: 'text-blue-600' },
  twitter:   { icon: FaTwitter,   color: 'text-sky-500' },
  linkedin:  { icon: FaLinkedin,  color: 'text-blue-700' },
  instagram: { icon: FaInstagram, color: 'text-pink-500' },
  pinterest: { icon: FaPinterest, color: 'text-red-600' },
  youtube:   { icon: FaYoutube,   color: 'text-red-600' },
  tiktok:    { icon: FaTiktok,    color: 'text-gray-900' },
  bluesky:   { icon: SiBluesky,   color: 'text-blue-500' },
  threads:   { icon: SiThreads,   color: 'text-gray-900' },
  discord:   { icon: FaDiscord,   color: 'text-indigo-500' },
};

const getAvatarColor = (name) => {
  const colors = [
    'bg-blue-500', 'bg-green-500', 'bg-yellow-500', 'bg-red-500',
    'bg-purple-500', 'bg-pink-500', 'bg-indigo-500', 'bg-teal-500',
  ];
  return colors[(name?.charCodeAt(0) || 0) % colors.length];
};

// ── Scroll Time Picker ────────────────────────────────────────────────────────
/** One drum-wheel column with ▲ / ▼ arrows and low-sensitivity scroll. */
const DrumColumn = ({ items, selected, onSelect, fmt, wrap = true }) => {
  const accumRef = useRef(0);          // scroll accumulator
  const THRESHOLD = 80;                // px of wheel delta to count as one step

  const idx = items.indexOf(selected);
  const f   = (v) => (fmt ? fmt(v) : String(v).padStart(2, '0'));

  const step = (delta) => {
    const newIdx = wrap
      ? (idx + delta + items.length) % items.length
      : Math.max(0, Math.min(items.length - 1, idx + delta));
    onSelect(items[newIdx]);
  };

  const handleWheel = (e) => {
    e.preventDefault();
    accumRef.current += e.deltaY;
    if (Math.abs(accumRef.current) >= THRESHOLD) {
      step(accumRef.current > 0 ? 1 : -1);
      accumRef.current = 0;
    }
  };

  return (
    <div
      className="flex flex-col items-center w-14 select-none"
      onWheel={handleWheel}
    >
      {/* ▲ up arrow */}
      <button
        type="button"
        onClick={() => step(-1)}
        className="w-full h-8 flex items-center justify-center text-gray-300 hover:text-blue-500 hover:bg-blue-50 rounded-t-xl transition-colors"
      >
        <FaChevronUp className="text-[10px]" />
      </button>

      {/* selected value with highlight */}
      <div className="relative w-full">
        <div className="absolute inset-x-1 inset-y-0 bg-blue-50 border border-blue-200 rounded-xl pointer-events-none" />
        <div className="relative z-10 h-11 flex items-center justify-center text-xl font-bold text-blue-600 cursor-default">
          {f(selected)}
        </div>
      </div>

      {/* ▼ down arrow */}
      <button
        type="button"
        onClick={() => step(1)}
        className="w-full h-8 flex items-center justify-center text-gray-300 hover:text-blue-500 hover:bg-blue-50 rounded-b-xl transition-colors"
      >
        <FaChevronDown className="text-[10px]" />
      </button>
    </div>
  );
};

/** Full drum-roll time picker bound to a "HH:MM" 24-hour string. */
const ScrollTimePicker = ({ value, onChange }) => {
  const [h24, rawMin] = (value || '14:00').split(':').map(Number);
  const isPM = h24 >= 12;
  const h12  = h24 % 12 || 12;
  const min  = rawMin;

  const commit = (newH12, newMin, newIsPM) => {
    const h = (newH12 % 12) + (newIsPM ? 12 : 0);
    onChange(`${String(h).padStart(2, '0')}:${String(newMin).padStart(2, '0')}`);
  };

  const hours   = Array.from({ length: 12 }, (_, i) => i + 1);
  const minutes = Array.from({ length: 60 }, (_, i) => i);

  return (
    <div className="flex items-center justify-center gap-1 py-1 select-none">
      <DrumColumn
        items={hours}   selected={h12}  wrap
        onSelect={(v) => commit(v, min, isPM)}
      />
      <span className="text-2xl font-bold text-gray-300 self-center">:</span>
      <DrumColumn
        items={minutes} selected={min}  wrap
        onSelect={(v) => commit(h12, v, isPM)}
      />

      {/* AM / PM toggle — height matches DrumColumn (h-8 + h-11 + h-8 = 108px total) */}
      <div className="flex flex-col ml-1 self-center gap-1">
        {['AM', 'PM'].map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => commit(h12, min, p === 'PM')}
            className={`w-10 h-[50px] rounded-xl text-xs font-bold transition-all ${
              (p === 'PM') === isPM
                ? 'bg-blue-600 text-white shadow-sm'
                : 'bg-offwhite border border-gray-200 text-gray-400 hover:bg-gray-50'
            }`}
          >
            {p}
          </button>
        ))}
      </div>
    </div>
  );
};

// ── Main Component ────────────────────────────────────────────────────────────
/**
 * Props:
 *   postTypeOverride – string – pass when used as modal (bypasses useParams)
 *   asModal          – bool   – render as 80%-screen modal overlay
 *   onClose          – fn     – called when back/close is clicked in modal mode
 */
const CreatePostForm = ({ postTypeOverride, asModal = false, onClose }) => {
  const { type: typeFromParam } = useParams();
  const type = postTypeOverride || typeFromParam;
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  const coverImageInputRef = useRef(null);

  // Drag-to-reorder refs
  const dragItemIdx    = useRef(null);
  const dragOverItemIdx = useRef(null);

  // ── Accounts ──────────────────────────────────────────────────────────────
  const [selectedAccounts, setSelectedAccounts]   = useState([]);
  const [availableAccounts, setAvailableAccounts] = useState([]);

  // ── Per-platform captions ─────────────────────────────────────────────────
  const [platformCaptions, setPlatformCaptions] = useState({});

  // ── Platform-specific settings ────────────────────────────────────────────
  const [postFormat,            setPostFormat]            = useState('Post');
  const [firstComment,          setFirstComment]          = useState('');
  const [location,              setLocation]              = useState('');
  const [shopGridLink,          setShopGridLink]          = useState('');
  const [videoTitle,            setVideoTitle]            = useState('');
  const [youtubePrivacy,        setYoutubePrivacy]        = useState('public');
  const [linkedinFirstComment,  setLinkedinFirstComment]  = useState('');
  const [linkedinDocumentUrl,   setLinkedinDocumentUrl]   = useState(null);
  const [linkedinDocumentTitle, setLinkedinDocumentTitle] = useState(null);
  const [tiktokPrivacy,         setTiktokPrivacy]         = useState('public');
  const [tiktokAllowDuet,       setTiktokAllowDuet]       = useState(true);
  const [tiktokAllowStitch,     setTiktokAllowStitch]     = useState(true);
  const [tiktokAllowComments,   setTiktokAllowComments]   = useState(true);

  // ── Upload state ──────────────────────────────────────────────────────────
  const [uploading,          setUploading]          = useState(false);
  const [uploadProgress,     setUploadProgress]     = useState(0);
  const [uploadedMedia,      setUploadedMedia]      = useState([]);   // array of {file,url,type,name,width,height}
  const [coverImage,         setCoverImage]         = useState(null);
  const [coverImageUploading,setCoverImageUploading]= useState(false);
  const [mediaRawAspectRatio,setMediaRawAspectRatio]= useState(null);
  const [hashtagGroups,      setHashtagGroups]      = useState([]);

  // ── Image cropper ─────────────────────────────────────────────────────────
  const [showCropper,      setShowCropper]      = useState(false);
  const [cropImageSrc,     setCropImageSrc]     = useState(null);
  const [cropTargetRatio,  setCropTargetRatio]  = useState(null);   // null = cover image mode
  const [cropMediaIndex,   setCropMediaIndex]   = useState(null);   // null = cover image mode
  const [crop,             setCrop]             = useState({ x: 0, y: 0 });
  const [zoom,             setZoom]             = useState(1);
  const [croppedAreaPixels,setCroppedAreaPixels]= useState(null);

  // ── UI state ──────────────────────────────────────────────────────────────
  const [rightPanelMode,        setRightPanelMode]        = useState('preview'); // 'preview' | 'ai'
  const [previewVisible,        setPreviewVisible]        = useState(true);
  const [activePreviewPlatform, setActivePreviewPlatform] = useState(null);
  // ── AI Assistant state ─────────────────────────────────────────────────────
  const [aiCaptionPrompt,       setAiCaptionPrompt]       = useState('');
  const [aiCaptionTone,         setAiCaptionTone]         = useState('casual');
  const [aiCaptionPlatform,     setAiCaptionPlatform]     = useState('all');
  const [aiCaptionLoading,      setAiCaptionLoading]      = useState(false);
  const [aiGeneratedText,       setAiGeneratedText]       = useState('');
  const [expandedPlatform,      setExpandedPlatform]      = useState(null);
  const [platformOrder,         setPlatformOrder]         = useState([]);
  const [createAnother,         setCreateAnother]         = useState(false);
  const [showSchedulePicker,    setShowSchedulePicker]    = useState(false);
  const [scheduledDate,         setScheduledDate]         = useState('');
  const [scheduledTime,         setScheduledTime]         = useState('14:00');
  const [selectedTimezone,      setSelectedTimezone]      = useState(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Kolkata'
  );
  const [loading,               setLoading]               = useState(false);
  const [altTexts,              setAltTexts]              = useState([]);

  // ── AI Image Generation state ─────────────────────────────────────────────
  const [showAiPanel,           setShowAiPanel]           = useState(false);
  const [aiPrompt,              setAiPrompt]              = useState('');
  const [aiSize,                setAiSize]                = useState('1024x1024');
  const [aiStyle,               setAiStyle]               = useState('vivid');
  const [aiGenerating,          setAiGenerating]          = useState(false);

  // ── Init ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    loadAccounts();
    loadHashtagGroups();
    setScheduledDate(new Date().toISOString().split('T')[0]);
  }, []);

  const loadAccounts = async () => {
    try {
      const accounts = await getSocialAccounts();
      setAvailableAccounts(accounts);
    } catch {
      setAvailableAccounts([]);
    }
  };

  const loadHashtagGroups = async () => {
    try {
      const groups = await getHashtagGroups();
      setHashtagGroups(groups || []);
    } catch {
      setHashtagGroups([]);
    }
  };

  // ── Keep platformOrder and expandedPlatform in sync ───────────────────────
  useEffect(() => {
    const platforms = [
      ...new Set(availableAccounts.filter(a => selectedAccounts.includes(a.id)).map(a => a.platform))
    ];

    // Maintain custom order: keep existing, append new ones
    setPlatformOrder(prev => {
      const existing = prev.filter(p => platforms.includes(p));
      const newOnes  = platforms.filter(p => !prev.includes(p));
      return [...existing, ...newOnes];
    });

    // Auto-expand first platform if none expanded (or expanded was removed)
    setExpandedPlatform(prev => {
      if (platforms.length === 0) return null;
      if (prev && platforms.includes(prev)) return prev;
      return platforms[0];
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAccounts, availableAccounts]);

  // ── Account helpers ───────────────────────────────────────────────────────
  const toggleAccountSelection = (id) => {
    setSelectedAccounts(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const getSelectedPlatforms = () =>
    [...new Set(availableAccounts.filter(a => selectedAccounts.includes(a.id)).map(a => a.platform))];

  const selectedPlatforms = getSelectedPlatforms();

  // Ordered list of platforms (respects manual drag order)
  const orderedPlatforms = platformOrder.filter(p => selectedPlatforms.includes(p));

  // Active platform for preview
  const activePlatform = (activePreviewPlatform && selectedPlatforms.includes(activePreviewPlatform))
    ? activePreviewPlatform
    : selectedPlatforms[0] || null;

  const activeAccount = availableAccounts.find(
    a => selectedAccounts.includes(a.id) && a.platform === activePlatform
  );

  // ── Accordion toggle ──────────────────────────────────────────────────────
  const handleToggleExpand = (platform) => {
    setExpandedPlatform(prev => {
      const next = prev === platform ? null : platform;
      // Sync preview with expanded platform
      if (next) setActivePreviewPlatform(next);
      return next;
    });
  };

  // ── Drag-to-reorder handlers ──────────────────────────────────────────────
  const handleDragStart = (index) => { dragItemIdx.current = index; };
  const handleDragEnter = (index) => { dragOverItemIdx.current = index; };
  const handleDragEnd   = () => {
    if (dragItemIdx.current === null || dragOverItemIdx.current === null) return;
    if (dragItemIdx.current === dragOverItemIdx.current) {
      dragItemIdx.current = null;
      dragOverItemIdx.current = null;
      return;
    }
    const list = [...orderedPlatforms];
    const [moved] = list.splice(dragItemIdx.current, 1);
    list.splice(dragOverItemIdx.current, 0, moved);
    setPlatformOrder(list);
    dragItemIdx.current    = null;
    dragOverItemIdx.current = null;
  };

  // ── Upload helpers ────────────────────────────────────────────────────────
  const getImageDimensions = (url) =>
    new Promise((resolve) => {
      const img = new Image();
      img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight });
      img.onerror = () => resolve({ width: 0, height: 0 });
      img.src = url;
    });

  const uploadToBackend = async (file) => {
    if (!file) return;
    const isVideo = file.type.startsWith('video/');

    // Validate mix of video + images
    setUploadedMedia(prev => {
      if (prev.length > 0) {
        if (prev[0].type === 'video') {
          toast.error('Remove the video before adding more media.');
          return prev;
        }
        if (isVideo) {
          toast.error('Remove existing images before adding a video.');
          return prev;
        }
      }
      return prev; // no change yet, actual append happens after upload
    });

    // Re-check synchronously via a local capture
    const currentMedia = uploadedMedia;
    if (currentMedia.length > 0 && (currentMedia[0].type === 'video' || isVideo)) return;

    setUploading(true);
    setUploadProgress(0);
    try {
      const response = await uploadMedia(file, (e) =>
        setUploadProgress(Math.round((e.loaded * 100) / e.total))
      );
      if (response.success) {
        const base = process.env.REACT_APP_BACKEND_URL || '';
        const mediaUrl = `${base}${response.url}`;
        const dims = isVideo ? { width: 0, height: 0 } : await getImageDimensions(mediaUrl);
        setUploadedMedia(prev => [
          ...prev,
          {
            file,
            url: mediaUrl,
            originalUrl: mediaUrl,
            type: isVideo ? 'video' : 'image',
            name: file.name,
            width: dims.width,
            height: dims.height,
          },
        ]);
        toast.success('Media uploaded');
      } else {
        throw new Error('Upload failed');
      }
    } catch {
      toast.error('Failed to upload media');
    } finally {
      setUploading(false);
    }
  };

  // Upload multiple files sequentially
  const uploadFilesToBackend = async (files) => {
    const arr = Array.isArray(files) ? files : Array.from(files);
    for (const f of arr) {
      await uploadToBackend(f);
    }
  };

  // Remove a single item by index
  const removeMediaItem = (index) => {
    setUploadedMedia(prev => prev.filter((_, i) => i !== index));
  };

  // Reorder media by dragging thumbnails
  const reorderMedia = (fromIndex, toIndex) => {
    setUploadedMedia(prev => {
      const arr = [...prev];
      const [moved] = arr.splice(fromIndex, 1);
      arr.splice(toIndex, 0, moved);
      return arr;
    });
  };

  const uploadCoverImageToBackend = async (file) => {
    if (!file) return;
    setCoverImageUploading(true);
    try {
      const response = await uploadMedia(file, () => {});
      if (response.success) {
        const base = process.env.REACT_APP_BACKEND_URL || '';
        setCoverImage(`${base}${response.url}`);
        toast.success('Cover image uploaded');
      }
    } catch {
      toast.error('Failed to upload cover image');
    } finally {
      setCoverImageUploading(false);
    }
  };

  // ── Cropper helpers ───────────────────────────────────────────────────────
  const onCropComplete = (_, pixels) => setCroppedAreaPixels(pixels);

  const createImage = (url) =>
    new Promise((resolve, reject) => {
      const img = new Image();
      img.addEventListener('load', () => resolve(img));
      img.addEventListener('error', reject);
      img.setAttribute('crossOrigin', 'anonymous');
      img.src = url;
    });

  const getCroppedImg = async (src, pixelCrop) => {
    const image = await createImage(src);
    const canvas = document.createElement('canvas');
    canvas.width = image.width;
    canvas.height = image.height;
    canvas.getContext('2d').drawImage(image, 0, 0);
    const cropped = document.createElement('canvas');
    cropped.width = pixelCrop.width;
    cropped.height = pixelCrop.height;
    cropped.getContext('2d').drawImage(
      canvas, pixelCrop.x, pixelCrop.y, pixelCrop.width, pixelCrop.height,
      0, 0, pixelCrop.width, pixelCrop.height
    );
    return new Promise((resolve, reject) => {
      cropped.toBlob(
        (blob) => blob ? resolve(blob) : reject(new Error('Empty canvas')),
        'image/jpeg'
      );
    });
  };

  const handleApplyCrop = async () => {
    try {
      const blob = await getCroppedImg(cropImageSrc, croppedAreaPixels);
      setShowCropper(false);
      setCropImageSrc(null);
      const file = new File([blob], 'cropped_image.jpg', { type: 'image/jpeg' });
      if (cropMediaIndex !== null) {
        // Crop a post media item — replace it in place
        const base = process.env.REACT_APP_BACKEND_URL || '';
        setUploading(true);
        try {
          const response = await uploadMedia(file, (e) =>
            setUploadProgress(Math.round((e.loaded * 100) / e.total))
          );
          if (response.success) {
            const mediaUrl = `${base}${response.url}`;
            const dims = await getImageDimensions(mediaUrl);
            setUploadedMedia(prev => {
              const next = [...prev];
              next[cropMediaIndex] = { ...next[cropMediaIndex], url: mediaUrl, file, width: dims.width, height: dims.height, originalUrl: next[cropMediaIndex].originalUrl || next[cropMediaIndex].url };
              return next;
            });
            toast.success('Image cropped');
          }
        } finally {
          setUploading(false);
          setCropMediaIndex(null);
          setCropTargetRatio(null);
        }
      } else {
        // Cover image crop
        uploadCoverImageToBackend(file);
        setCropTargetRatio(null);
      }
    } catch {
      toast.error('Failed to crop image');
    }
  };

  // Called from PlatformEditor "Crop" button
  const handleCropMedia = (index, targetRatio) => {
    const item = uploadedMedia[index];
    if (!item || item.type === 'video') return;
    setCropMediaIndex(index);
    setCropTargetRatio(targetRatio);
    setCropImageSrc(item.originalUrl || item.url);
    setCrop({ x: 0, y: 0 });
    setZoom(1);
    setShowCropper(true);
  };

  const handleCoverImageChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (type === 'video' && mediaRawAspectRatio) {
      const reader = new FileReader();
      reader.addEventListener('load', () => { setCropImageSrc(reader.result); setShowCropper(true); });
      reader.readAsDataURL(file);
    } else {
      uploadCoverImageToBackend(file);
    }
    e.target.value = null;
  };

  // ── Reset (Create Another) ────────────────────────────────────────────────
  const resetForm = () => {
    setPlatformCaptions({});
    setUploadedMedia([]);
    setCoverImage(null);
    setFirstComment('');
    setLocation('');
    setShopGridLink('');
    setVideoTitle('');
    setLinkedinFirstComment('');
    setYoutubePrivacy('public');
    setPostFormat('Post');
  };

  // ── Submit ────────────────────────────────────────────────────────────────
  const handleSubmit = async (mode) => {
    const primaryPlatform = orderedPlatforms[0] || selectedPlatforms[0];
    const primaryContent  = (primaryPlatform ? platformCaptions[primaryPlatform] : '') || '';
    const hasContent      = selectedPlatforms.some(p => (platformCaptions[p] || '').trim());

    if (!hasContent) {
      toast.error('Please enter some content for at least one platform');
      return;
    }
    if (selectedAccounts.length === 0) {
      toast.error('Please select at least one account');
      return;
    }

    setLoading(true);
    try {
      const token  = localStorage.getItem('token');
      const apiUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';

      let scheduledDateTime = null;
      let status;

      if (mode === 'draft') {
        status = 'draft';
      } else if (mode === 'now') {
        scheduledDateTime = new Date().toISOString();
        status = 'scheduled';
      } else if (mode === 'scheduled') {
        if (!scheduledDate || !scheduledTime) {
          toast.error('Please pick a date and time'); setLoading(false); return;
        }
        scheduledDateTime = localToUTC(scheduledDate, scheduledTime, selectedTimezone);
        if (!scheduledDateTime) { toast.error('Invalid date / time'); setLoading(false); return; }
        status = 'scheduled';
      }

      await axios.post(`${apiUrl}/api/posts`, {
        content: primaryContent,
        platforms: selectedPlatforms,
        accounts: selectedAccounts,
        scheduled_time: scheduledDateTime,
        status,
        post_type: type,
        cover_image: coverImage,
        media_urls: uploadedMedia.map(m => m.url),
      media_alt_texts: altTexts,
        youtube_title: videoTitle,
        youtube_privacy: youtubePrivacy,
        instagram_post_format: postFormat,
        instagram_first_comment: firstComment,
        instagram_location: location,
        instagram_shop_grid_link: shopGridLink,
        linkedin_document_url: linkedinDocumentUrl,
        linkedin_document_title: linkedinDocumentTitle,
        tiktok_privacy: tiktokPrivacy,
        tiktok_allow_duet: tiktokAllowDuet,
        tiktok_allow_stitch: tiktokAllowStitch,
        tiktok_allow_comments: tiktokAllowComments,
        platform_specific_content: platformCaptions,
      }, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
        withCredentials: true,
        timeout: 15000,
      });

      toast.success(
        mode === 'draft' ? 'Draft saved!' :
        mode === 'now'   ? 'Post published!' :
        'Post scheduled!'
      );

      if (createAnother) {
        resetForm();
      } else {
        navigate('/content');
        onClose?.();
      }
    } catch (err) {
      console.error(err);
      toast.error('Failed to create post');
    } finally {
      setLoading(false);
    }
  };

  const handleBack = () => {
    if (onClose) {
      onClose();
    } else {
      navigate('/create');
    }
  };

  // ── Build reusable JSX sections ───────────────────────────────────────────

  /** Top header bar */
  const headerBar = (
    <div className="h-16 bg-white border-b-2 border-gray-200 flex items-center justify-between px-5 flex-shrink-0 z-10 shadow-sm">
      <div className="flex items-center gap-4">
        <button onClick={handleBack} className="p-2 rounded-lg hover:bg-gray-100 transition-colors text-gray-600 hover:text-gray-900">
          <FaArrowLeft className="text-lg" />
        </button>
        <div>
          <h1 className="text-lg font-bold text-gray-900">Create Post</h1>
          {selectedAccounts.length > 0 && (
            <span className="text-xs text-gray-500">
              {selectedAccounts.length} account{selectedAccounts.length !== 1 ? 's' : ''} selected
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2 bg-gray-100 rounded-lg p-1">
        <Button
          variant={rightPanelMode === 'ai' ? 'default' : 'ghost'}
          size="sm"
          onClick={() => setRightPanelMode(m => m === 'ai' ? 'preview' : 'ai')}
          className={`gap-2 text-xs font-bold rounded-md transition-all ${rightPanelMode === 'ai' ? 'bg-white text-violet-600 shadow-sm' : 'text-gray-600 hover:text-gray-900'}`}
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
          </svg>
          AI
        </Button>
        <Button
          variant={rightPanelMode === 'preview' && previewVisible ? 'default' : 'ghost'}
          size="sm"
          onClick={() => { setRightPanelMode('preview'); setPreviewVisible(v => !v); }}
          className={`gap-2 text-xs font-bold rounded-md transition-all ${rightPanelMode === 'preview' && previewVisible ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-600 hover:text-gray-900'}`}
        >
          {previewVisible && rightPanelMode === 'preview' ? <FaEye className="text-xs" /> : <FaEyeSlash className="text-xs" />}
          Preview
        </Button>
        {/* Close button in modal mode */}
        {asModal && (
          <button onClick={onClose} className="ml-2 p-2 rounded-lg hover:bg-gray-200 transition-colors text-gray-600 hover:text-gray-900">
            <FaTimes className="text-lg" />
          </button>
        )}
      </div>
    </div>
  );

  /** Account selector strip */
  const accountStrip = (
    <div className="bg-white border-b-2 border-gray-200 px-5 py-4 flex-shrink-0">
      <AccountSelector
        accounts={availableAccounts}
        selectedAccounts={selectedAccounts}
        onToggle={toggleAccountSelection}
        platformIcons={platformIcons}
        getAvatarColor={getAvatarColor}
        onSetActive={(platform) => {
          setActivePreviewPlatform(platform);
          setExpandedPlatform(platform);
        }}
      />
    </div>
  );

  /** Left panel: stacked PlatformEditors */
  const leftPanel = (
    <div className="flex-1 overflow-y-auto p-6 min-w-0 bg-offwhite">
      {orderedPlatforms.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-28 text-center">
          <div className="w-20 h-20 rounded-full bg-white border-2 border-gray-200 flex items-center justify-center mb-5 shadow-sm">
            <svg className="w-8 h-8 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M17 8h2a2 2 0 012 2v6a2 2 0 01-2 2h-2v4l-4-4H9a1.994 1.994 0 01-1.414-.586m0 0L11 14h4a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2v4l.586-.586z" />
            </svg>
          </div>
          <p className="text-base font-bold text-gray-700">No platforms selected</p>
          <p className="text-sm text-gray-500 mt-2">Select one or more accounts above to start creating your post</p>
        </div>
      ) : (
        <>
          {/* ── AI Image Generation card (image/carousel posts only) ── */}
          {(type === 'image' || type === 'carousel') && uploadedMedia.length === 0 && (
            <div className="bg-white rounded-xl border-2 border-purple-200 shadow-sm p-5 mb-5 hover:border-purple-300 transition-colors">
              <button
                onClick={() => setShowAiPanel(v => !v)}
                className="flex items-center gap-2.5 text-sm font-bold text-purple-700 hover:text-purple-900 transition-colors w-full text-left"
              >
                <FaMagic className="text-sm" />
                {showAiPanel ? 'Hide AI Image Generator' : '✨ Generate image with AI (DALL-E 3)'}
              </button>
              {showAiPanel && (
                <div className="mt-3">
                  <textarea
                    value={aiPrompt}
                    onChange={e => setAiPrompt(e.target.value)}
                    placeholder="Describe the image you want to generate…"
                    rows={3}
                    className="w-full border border-purple-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-300 placeholder:text-gray-400 resize-none mb-2 bg-purple-50/30"
                  />
                  <div className="flex gap-2 mb-2">
                    <select
                      value={aiSize}
                      onChange={e => setAiSize(e.target.value)}
                      className="flex-1 text-xs border border-purple-200 rounded-lg px-2 py-1.5 bg-offwhite focus:outline-none focus:ring-2 focus:ring-purple-300"
                    >
                      <option value="1024x1024">Square 1:1</option>
                      <option value="1792x1024">Landscape 16:9</option>
                      <option value="1024x1792">Portrait 9:16</option>
                    </select>
                    <select
                      value={aiStyle}
                      onChange={e => setAiStyle(e.target.value)}
                      className="flex-1 text-xs border border-purple-200 rounded-lg px-2 py-1.5 bg-offwhite focus:outline-none focus:ring-2 focus:ring-purple-300"
                    >
                      <option value="vivid">Vivid</option>
                      <option value="natural">Natural</option>
                    </select>
                  </div>
                  <button
                    disabled={aiGenerating || !aiPrompt.trim()}
                    onClick={async () => {
                      if (!aiPrompt.trim()) return;
                      setAiGenerating(true);
                      try {
                        const data = await generateImage(aiPrompt.trim(), aiSize, aiStyle);
                        setUploadedMedia(prev => [...prev, { url: data.url, type: 'image', name: 'ai-generated.png' }]);
                        toast.success('Image generated!');
                        setShowAiPanel(false);
                        setAiPrompt('');
                      } catch (err) {
                        toast.error(err?.response?.data?.detail || 'Failed to generate image');
                      } finally {
                        setAiGenerating(false);
                      }
                    }}
                    className="w-full py-2 text-sm font-semibold bg-purple-600 hover:bg-purple-700 text-white rounded-lg disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
                  >
                    {aiGenerating ? (
                      <><div className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />Generating…</>
                    ) : (
                      <><FaMagic className="text-xs" />Generate</>
                    )}
                  </button>
                </div>
              )}
            </div>
          )}

          {orderedPlatforms.map((platform, index) => (
            <PlatformEditor
              key={platform}
              platform={platform}
              postType={type}
              content={platformCaptions[platform] ?? ''}
              onContentChange={(val) =>
                setPlatformCaptions(prev => ({ ...prev, [platform]: val }))
              }
              // Accordion
              isExpanded={expandedPlatform === platform}
              onToggleExpand={() => handleToggleExpand(platform)}
              // Drag-to-reorder
              onDragStart={() => handleDragStart(index)}
              onDragEnter={() => handleDragEnter(index)}
              onDragEnd={handleDragEnd}
              onDragOver={(e) => e.preventDefault()}
              // Media (only first platform has upload controls)
              media={uploadedMedia}
              uploading={index === 0 ? uploading : false}
              uploadProgress={index === 0 ? uploadProgress : 0}
              onFilesSelect={index === 0 ? uploadFilesToBackend : null}
              onRemoveMedia={index === 0 ? removeMediaItem : null}
              onReorderMedia={index === 0 ? reorderMedia : null}
              fileInputRef={index === 0 ? fileInputRef : null}
              // Platform-specific
              postFormat={postFormat}             onPostFormatChange={setPostFormat}
              firstComment={firstComment}        onFirstCommentChange={setFirstComment}
              location={location}                onLocationChange={setLocation}
              shopGridLink={shopGridLink}        onShopGridLinkChange={setShopGridLink}
              videoTitle={videoTitle}            onVideoTitleChange={setVideoTitle}
              youtubePrivacy={youtubePrivacy}    onYoutubePrivacyChange={setYoutubePrivacy}
              linkedinFirstComment={linkedinFirstComment} onLinkedinFirstCommentChange={setLinkedinFirstComment}
              linkedinDocumentUrl={linkedinDocumentUrl}
              linkedinDocumentTitle={linkedinDocumentTitle}
              tiktokPrivacy={tiktokPrivacy} onTiktokPrivacyChange={setTiktokPrivacy}
              tiktokAllowDuet={tiktokAllowDuet} onTiktokAllowDuetChange={setTiktokAllowDuet}
              tiktokAllowStitch={tiktokAllowStitch} onTiktokAllowStitchChange={setTiktokAllowStitch}
              tiktokAllowComments={tiktokAllowComments} onTiktokAllowCommentsChange={setTiktokAllowComments}
              onLinkedinDocumentChange={async ({ file, url, title }) => {
                if (file) {
                  try {
                    const result = await uploadMedia(file);
                    setLinkedinDocumentUrl(result.url);
                    setLinkedinDocumentTitle(title || file.name.replace(/\.[^.]+$/, ''));
                  } catch { toast.error('Failed to upload document'); }
                } else {
                  setLinkedinDocumentUrl(url || null);
                  setLinkedinDocumentTitle(title || null);
                }
              }}
              altTexts={index === 0 ? altTexts : []}
              onAltTextsChange={index === 0 ? setAltTexts : undefined}
              // Crop + Hashtags
              onCropMedia={handleCropMedia}
              hashtagGroups={hashtagGroups}
            />
          ))}

          {/* Cover image card (video + uploaded media) */}
          {type === 'video' && uploadedMedia.length > 0 && (
            <div className="bg-white rounded-xl border-2 border-gray-200 shadow-sm p-5 mb-5 hover:border-blue-300 transition-colors">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-bold text-gray-800">Cover Image</span>
                <button onClick={() => coverImageInputRef.current?.click()} className="text-xs text-blue-600 hover:text-blue-700 font-bold">
                  {coverImage ? 'Change' : '+ Add cover'}
                </button>
              </div>
              {coverImage ? (
                <div className="relative rounded-lg overflow-hidden group">
                  <img src={coverImage} alt="Cover" className="w-full object-cover" style={{ aspectRatio: mediaRawAspectRatio || '16/9' }} />
                  <button onClick={() => setCoverImage(null)} className="absolute top-2 right-2 w-6 h-6 rounded-full bg-black/50 text-white flex items-center justify-center text-xs opacity-0 group-hover:opacity-100 transition-opacity">✕</button>
                </div>
              ) : coverImageUploading ? (
                <div className="h-16 flex items-center justify-center text-sm text-gray-400">Uploading…</div>
              ) : (
                <div onClick={() => coverImageInputRef.current?.click()} className="h-16 border-2 border-dashed border-gray-200 rounded-lg flex items-center justify-center cursor-pointer hover:border-blue-300 hover:bg-blue-50/30 transition-all text-sm text-gray-400">
                  Click to add cover image
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );

  /** AI caption generation handler */
  const handleGenerateCaption = async () => {
    if (!aiCaptionPrompt.trim()) return;
    setAiCaptionLoading(true);
    setAiGeneratedText('');
    try {
      const platform = aiCaptionPlatform === 'all' ? null : aiCaptionPlatform;
      const data = await generateContent(aiCaptionPrompt.trim(), platform, aiCaptionTone);
      setAiGeneratedText(data.content);
      // Also inject into caption editors if platforms are selected
      if (aiCaptionPlatform === 'all') {
        const updates = {};
        orderedPlatforms.forEach(p => { updates[p] = data.content; });
        if (Object.keys(updates).length > 0) {
          setPlatformCaptions(prev => ({ ...prev, ...updates }));
        }
      } else {
        setPlatformCaptions(prev => ({ ...prev, [aiCaptionPlatform]: data.content }));
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'AI generation failed. Check your API keys.');
    } finally {
      setAiCaptionLoading(false);
    }
  };

  const handleApplyGeneratedText = () => {
    if (!aiGeneratedText) return;
    if (aiCaptionPlatform === 'all') {
      const updates = {};
      orderedPlatforms.forEach(p => { updates[p] = aiGeneratedText; });
      setPlatformCaptions(prev => ({ ...prev, ...updates }));
    } else {
      setPlatformCaptions(prev => ({ ...prev, [aiCaptionPlatform]: aiGeneratedText }));
    }
    toast.success('✨ Applied to caption editor!');
  };

  /** Right panel: AI Assistant or Preview */
  const AI_TONES = [
    { id: 'casual',       label: 'Casual' },
    { id: 'professional', label: 'Professional' },
    { id: 'fun',          label: 'Fun' },
    { id: 'promotional',  label: 'Promotional' },
  ];

  const aiPanel = (
    <div className="w-[340px] border-l border-gray-200 bg-offwhite overflow-y-auto flex-shrink-0 flex flex-col">
      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-600 to-violet-700 flex items-center justify-center shadow-sm">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
            </svg>
          </div>
          <span className="text-sm font-bold text-gray-900">AI Assistant</span>
        </div>
        {/* Active platform icon badge */}
        {activePlatform && platformIcons[activePlatform] && (() => {
          const { icon: Icon, color } = platformIcons[activePlatform];
          return <Icon className={`text-lg ${color}`} />;
        })()}
      </div>

      {/* Body - scrollable */}
      <div className="p-5 space-y-4.5 overflow-y-auto flex-1">
        {/* Prompt textarea */}
        <div>
          <label className="block text-xs font-bold text-gray-700 mb-2">
            What do you want to write about?
          </label>
          <textarea
            value={aiCaptionPrompt}
            onChange={e => setAiCaptionPrompt(e.target.value)}
            placeholder="Eg. Promote my photography course to get new signups. Registration closes in 3 days."
            rows={5}
            className="w-full border-2 border-gray-200 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-violet-300 focus:border-violet-300 placeholder:text-gray-400 resize-none bg-white hover:border-gray-300 transition-colors"
          />
        </div>

        {/* Tone pills */}
        <div>
          <label className="block text-xs font-bold text-gray-700 mb-2.5">Tone</label>
          <div className="flex flex-wrap gap-2">
            {AI_TONES.map(t => (
              <button
                key={t.id}
                onClick={() => setAiCaptionTone(t.id)}
                className={`px-3.5 py-1.5 rounded-full text-xs font-semibold border-2 transition-all duration-200 ${
                  aiCaptionTone === t.id
                    ? 'bg-violet-600 text-white border-violet-600 shadow-md'
                    : 'bg-white text-gray-600 border-gray-200 hover:border-violet-400 hover:text-violet-600 hover:bg-violet-50/50'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Generate button */}
        <button
          disabled={aiCaptionLoading || !aiCaptionPrompt.trim()}
          onClick={handleGenerateCaption}
          className="w-full py-2.5 text-sm font-bold bg-gradient-to-r from-violet-600 to-violet-700 hover:from-violet-700 hover:to-violet-800 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl transition-all duration-200 flex items-center justify-center gap-2.5 shadow-md hover:shadow-lg"
        >
          {aiCaptionLoading ? (
            <>
              <div className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
              Generating…
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round"
                  d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
              </svg>
              Generate Content
            </>
          )}
        </button>

        {/* Pro tip */}
        <p className="text-xs text-gray-500 leading-relaxed bg-blue-50/60 rounded-lg px-3 py-2 border border-blue-100">
          <span className="font-bold text-blue-700">💡 Pro tip:</span>{' '}
          <span className="text-blue-600">Include key points, target audience, and desired outcome.</span>
        </p>

        {/* Generated output */}
        {aiGeneratedText && (
          <div className="rounded-xl border-2 border-violet-200 bg-violet-50 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 bg-violet-100/60 border-b-2 border-violet-200">
              <span className="text-xs font-bold text-violet-700">✨ Generated Content</span>
              <button
                onClick={handleApplyGeneratedText}
                className="text-xs font-bold text-white bg-violet-600 hover:bg-violet-700 px-3 py-1.5 rounded-lg transition-colors duration-200 shadow-sm hover:shadow-md"
              >
                Use this →
              </button>
            </div>
            <textarea
              readOnly
              value={aiGeneratedText}
              rows={6}
              className="w-full text-sm text-gray-700 bg-violet-50 p-3 resize-none border-none outline-none leading-relaxed"
            />
          </div>
        )}

      </div>
    </div>
  );

  const previewPanelContent = (
    <div className="w-[340px] border-l-2 border-gray-200 bg-offwhite overflow-y-auto flex-shrink-0 flex flex-col">
      <div className="p-5 flex-1">
        {activePlatform ? (
          <>
            <div className="flex items-center gap-2.5 mb-5">
              <span className="text-sm font-bold text-gray-900 capitalize">{activePlatform} Preview</span>
              <FaInfoCircle className="text-gray-400 text-xs" />
            </div>
            <PreviewPanel
              activePlatform={activePlatform}
              account={activeAccount}
              content={platformCaptions[activePlatform] ?? ''}
              media={uploadedMedia}
              videoTitle={videoTitle}
              postFormat={postFormat}
            />
            {selectedPlatforms.length > 1 && (
              <p className="text-xs text-gray-400 mt-4 text-center font-medium">
                Click a different account to switch preview
              </p>
            )}
          </>
        ) : (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-16 h-16 rounded-full bg-white border-2 border-gray-200 flex items-center justify-center mb-4">
              <FaEye className="text-gray-400 text-2xl" />
            </div>
            <p className="text-sm font-bold text-gray-700">No account selected</p>
            <p className="text-xs text-gray-500 mt-2">Select an account above to see the preview</p>
          </div>
        )}
      </div>
    </div>
  );

  const rightPanel = rightPanelMode === 'ai'
    ? aiPanel
    : (previewVisible ? previewPanelContent : null);

  /** Fixed bottom action bar */
  const bottomBar = (
    <div className="h-16 bg-white border-t-2 border-gray-200 flex items-center justify-between px-5 flex-shrink-0 z-10 shadow-lg">
      <label className="flex items-center gap-2.5 cursor-pointer hover:opacity-70 transition-opacity">
        <Checkbox
          checked={createAnother}
          onCheckedChange={(v) => setCreateAnother(!!v)}
          className="data-[state=checked]:bg-blue-600 data-[state=checked]:border-blue-600"
        />
        <span className="text-sm font-medium text-gray-700">Create Another</span>
      </label>

      <div className="flex items-center gap-3">
        {/* Save Drafts */}
        <Button
          variant="outline" size="sm"
          onClick={() => handleSubmit('draft')}
          disabled={loading}
          className="text-gray-700 border-2 border-gray-300 h-9 font-semibold hover:border-gray-400 hover:bg-gray-50 transition-colors"
        >
          Save Drafts
        </Button>

        {/* Post Now */}
        <Button
          size="sm"
          onClick={() => handleSubmit('now')}
          disabled={loading}
          className="h-9 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 text-white font-bold px-6 shadow-md hover:shadow-lg transition-all disabled:opacity-50"
        >
          {loading ? 'Posting…' : 'Post Now'}
        </Button>

        {/* Schedule */}
        <Button
          variant="outline" size="sm"
          onClick={() => setShowSchedulePicker(true)}
          disabled={loading}
          className="h-9 gap-2 text-gray-700 border-2 border-gray-300 font-semibold hover:border-blue-400 hover:text-blue-600 hover:bg-blue-50/50 transition-colors"
        >
          <FaClock className="text-xs" />
          Schedule
        </Button>
      </div>
    </div>
  );

  /** Dialogs (portaled to body via Radix, safe to render anywhere) */
  const dialogs = (
    <>
      {/* Hidden file inputs */}
      <input ref={coverImageInputRef} type="file" accept="image/*" onChange={handleCoverImageChange} className="hidden" />

      {/* ── Rich Schedule Picker ───────────────────────────────────────────── */}
      {(() => {
        // Build timezone options — always include user's detected TZ at the top
        const detectedTZ = Intl.DateTimeFormat().resolvedOptions().timeZone;
        const inList = TIMEZONES.find(tz => tz.value === detectedTZ);
        const tzOptions = inList
          ? TIMEZONES
          : [{ value: detectedTZ, label: `Local — ${detectedTZ.replace(/_/g, ' ')}` }, ...TIMEZONES];

        // Suggested slot times (next 2 upcoming hours, rounded)
        const now = new Date();
        const slots = [1, 2].map(i => {
          const d = new Date(now.getTime() + i * 60 * 60 * 1000);
          d.setMinutes(0, 0, 0);
          return `${String(d.getHours()).padStart(2, '0')}:00`;
        });

        // Best times per platform (industry benchmarks, 24h format)
        const BEST_TIMES = {
          instagram: ['06:00', '12:00', '18:00'],
          facebook:  ['09:00', '13:00', '16:00'],
          twitter:   ['08:00', '12:00', '17:00'],
          linkedin:  ['07:00', '12:00', '17:00'],
          youtube:   ['15:00', '19:00', '21:00'],
          tiktok:    ['06:00', '10:00', '19:00'],
          pinterest: ['20:00', '21:00', '22:00'],
          bluesky:   ['08:00', '12:00', '18:00'],
          threads:   ['09:00', '13:00', '19:00'],
        };
        // Compute union of best times for all selected platforms, sorted, deduped
        const bestTimes = [...new Set(
          selectedPlatforms.flatMap(p => BEST_TIMES[p] || [])
        )].sort().slice(0, 5);

        return (
          <Dialog open={showSchedulePicker} onOpenChange={setShowSchedulePicker}>
            <DialogContent className="max-w-[310px] p-0 overflow-hidden rounded-2xl gap-0">
              {/* Header */}
              <DialogHeader className="px-4 pt-4 pb-2.5 border-b border-gray-100">
                <DialogTitle className="text-sm font-semibold text-gray-900">Schedule Post</DialogTitle>
              </DialogHeader>

              <div className="overflow-y-auto" style={{ maxHeight: '85vh' }}>
                {/* Calendar — centred */}
                <div className="flex justify-center pt-2 pb-0">
                  <Calendar
                    mode="single"
                    selected={scheduledDate ? new Date(scheduledDate + 'T00:00:00') : undefined}
                    onSelect={(day) => {
                      if (day) setScheduledDate(day.toLocaleDateString('en-CA'));
                    }}
                    disabled={(date) => date < new Date(new Date().setHours(0, 0, 0, 0))}
                    initialFocus
                    className="border-0 p-0"
                  />
                </div>

                <div className="px-4 pb-4 space-y-3 pt-1">
                  {/* Best Times to Post */}
                  {bestTimes.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-gray-600 mb-1">
                        ✨ Best times to post
                        <span className="ml-1 text-[10px] font-normal text-gray-400">
                          ({selectedPlatforms.slice(0, 3).join(', ')}{selectedPlatforms.length > 3 ? '…' : ''})
                        </span>
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {bestTimes.map(t => (
                          <button
                            key={t}
                            onClick={() => setScheduledTime(t)}
                            className={`px-2.5 py-1 rounded-lg border text-[11px] font-medium transition-all ${
                              scheduledTime === t
                                ? 'bg-green-600 text-white border-green-600'
                                : 'border-green-200 text-green-700 bg-green-50 hover:border-green-400 hover:bg-green-100'
                            }`}
                          >
                            {fmt12h(t)}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Posting Slots */}
                  <div>
                    <p className="text-xs font-semibold text-gray-600 mb-1.5">Posting Slots</p>
                    <div className="flex gap-2">
                      {slots.map(t => (
                        <button
                          key={t}
                          onClick={() => setScheduledTime(t)}
                          className={`px-3 py-1.5 rounded-lg border text-xs font-semibold transition-all ${
                            scheduledTime === t
                              ? 'bg-blue-600 text-white border-blue-600'
                              : 'border-gray-200 text-gray-700 hover:border-blue-300 hover:bg-blue-50'
                          }`}
                        >
                          {fmt12h(t)}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Drum-roll time picker */}
                  <div>
                    <p className="text-xs font-semibold text-gray-600 mb-1.5">Select Time</p>
                    <div className="border-2 border-blue-200 rounded-xl bg-blue-50/30 overflow-hidden">
                      <ScrollTimePicker value={scheduledTime} onChange={setScheduledTime} />
                    </div>
                  </div>

                  {/* Timezone dropdown */}
                  <div>
                    <p className="text-xs font-semibold text-gray-600 mb-1.5">Timezone</p>
                    <select
                      value={selectedTimezone}
                      onChange={(e) => setSelectedTimezone(e.target.value)}
                      className="w-full border border-gray-200 rounded-xl px-3 py-2 text-xs text-gray-700 bg-offwhite focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-200"
                    >
                      {tzOptions.map(tz => (
                        <option key={tz.value} value={tz.value}>{tz.label}</option>
                      ))}
                    </select>
                  </div>

                  {/* Summary pill */}
                  {scheduledDate && scheduledTime && (
                    <div className="flex items-center gap-2 px-3 py-2 bg-blue-50 rounded-xl border border-blue-100">
                      <FaClock className="text-blue-400 text-[10px] flex-shrink-0" />
                      <p className="text-[11px] text-blue-700 font-medium leading-snug">
                        {new Date(scheduledDate + 'T00:00:00').toLocaleDateString('en-US', {
                          weekday: 'short', month: 'short', day: 'numeric'
                        })}
                        {' at '}
                        {fmt12h(scheduledTime)}
                        {' · '}
                        {selectedTimezone.split('/').pop().replace(/_/g, ' ')}
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {/* Footer */}
              <div className="px-4 py-3 border-t border-gray-100 flex gap-2">
                <Button
                  variant="outline" size="sm"
                  onClick={() => setShowSchedulePicker(false)}
                  className="flex-1 h-9 text-xs"
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  disabled={!scheduledDate || !scheduledTime || loading}
                  onClick={() => {
                    setShowSchedulePicker(false);
                    handleSubmit('scheduled');
                  }}
                  className="flex-1 h-9 bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs"
                >
                  {loading ? 'Scheduling…' : 'Schedule Post'}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        );
      })()}

      {/* Crop dialog */}
      <Dialog open={showCropper} onOpenChange={(open) => { setShowCropper(open); if (!open) { setCropMediaIndex(null); setCropTargetRatio(null); } }}>
        <DialogContent className="max-w-3xl h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>
              {cropMediaIndex !== null ? 'Crop Image' : 'Crop Cover Image'}
              {cropTargetRatio && (
                <span className="ml-2 text-sm font-normal text-gray-400">
                  Target ratio: {
                    Math.abs(cropTargetRatio - 9/16) < 0.01 ? '9:16' :
                    Math.abs(cropTargetRatio - 4/5) < 0.01 ? '4:5' :
                    Math.abs(cropTargetRatio - 1) < 0.01 ? '1:1' :
                    Math.abs(cropTargetRatio - 16/9) < 0.01 ? '16:9' :
                    Math.abs(cropTargetRatio - 2/3) < 0.01 ? '2:3' :
                    cropTargetRatio.toFixed(2)
                  }
                </span>
              )}
            </DialogTitle>
          </DialogHeader>
          <div className="flex-1 relative bg-gray-900 rounded-md overflow-hidden min-h-0">
            {cropImageSrc && (
              <Cropper
                image={cropImageSrc}
                crop={crop}
                zoom={zoom}
                aspect={cropTargetRatio || mediaRawAspectRatio || 16 / 9}
                onCropChange={setCrop}
                onCropComplete={onCropComplete}
                onZoomChange={setZoom}
                objectFit="contain"
              />
            )}
          </div>
          <div className="pt-4 flex justify-between items-center shrink-0 border-t mt-2">
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500">Zoom:</span>
              <input type="range" value={zoom} min={1} max={3} step={0.1} onChange={(e) => setZoom(Number(e.target.value))} className="w-32" />
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => { setShowCropper(false); setCropMediaIndex(null); setCropTargetRatio(null); }}>Cancel</Button>
              <Button size="sm" onClick={handleApplyCrop} className="bg-green-500 hover:bg-green-600">Crop & Upload</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );

  // ── Render (modal vs full-page) ───────────────────────────────────────────

  const formContent = (isModalMode) => (
    <div className={`flex flex-col bg-offwhite overflow-hidden ${isModalMode ? 'w-full h-full rounded-2xl' : 'h-screen'}`}>
      {headerBar}
      {accountStrip}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {leftPanel}
        {rightPanel}
      </div>
      {bottomBar}
    </div>
  );

  if (asModal) {
    return (
      <>
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
          onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}
        >
          <div
            className="shadow-2xl overflow-hidden rounded-2xl"
            style={{ width: '88vw', height: '88vh', maxWidth: '1500px' }}
          >
            {formContent(true)}
          </div>
        </div>
        {dialogs}
      </>
    );
  }

  return (
    <>
      {formContent(false)}
      {dialogs}
    </>
  );
};

export default CreatePostForm;
